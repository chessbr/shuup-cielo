# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

import copy
from decimal import Decimal
import json
import uuid

from django.core.urlresolvers import reverse
from mock import patch
import pytest

from cielo_webservice.request import CieloRequest
from shuup.core.defaults.order_statuses import create_default_order_statuses
from shuup.core.models._product_shops import ShopProduct
from shuup.core.models._service_behavior import FixedCostBehaviorComponent
from shuup.testing.factories import (
    get_default_product, get_default_shipping_method, get_default_shop, get_default_supplier,
    get_default_tax_class
)
from shuup.testing.mock_population import populate_if_required
from shuup.utils.i18n import format_money
from shuup.xtheme._theme import set_current_theme
from shuup_cielo.constants import (
    CIELO_SERVICE_CREDIT, CieloCardBrand, CieloProduct, CieloTransactionStatus,
    InterestType
)
from shuup_cielo.models import (
    CieloConfig, CieloPaymentProcessor, CieloTransaction, InstallmentContext
)
from shuup_cielo_tests import (
    AUTH_URL, CC_VISA_1X_INFO, get_approved_transaction, get_cancelled_transaction,
    get_captured_transaction, get_in_progress_transaction
)
from shuup_cielo_tests.test_checkout import get_payment_provider
from shuup_tests.front.test_checkout_flow import fill_address_inputs
from shuup_tests.utils import SmartClient

PRODUCT_PRICE = Decimal(13.43)
PRODUCT_QTNTY = 10
INSTALLMENTS_PATH = reverse("shuup:cielo_get_installment_options")
TRANSACTION_PATH = reverse("shuup:cielo_make_transaction")


def _configure_basket(client):
    """
    * Adds a product
    * Sets a default shipping method
    * Sets a CieloPaymentProcessor payment method
    * Sets user address
    """

    default_product = get_default_product()
    sp = ShopProduct.objects.get(product=default_product, shop=get_default_shop())
    sp.default_price = get_default_shop().create_price(PRODUCT_PRICE)
    sp.save()

    basket_path = reverse("shuup:basket")
    client.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": PRODUCT_QTNTY,
        "supplier": get_default_supplier().pk
    })

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()
    assert isinstance(processor, CieloPaymentProcessor)

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})

    # Phase: Addresses
    addresses_soup = client.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    client.post(addresses_path, data=inputs)

    # Phase: Methods
    client.post(
        reverse("shuup:checkout", kwargs={"phase": "methods"}),
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )


def _get_configured_basket_client():
    """
    Initialized and configure client
    adding product and setting address,
    ready to make transactions
    """
    get_default_shop()
    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')
    c = SmartClient()
    _configure_basket(c)
    return c


@pytest.mark.django_db
def test_get_installments_options_rest():
    shop = get_default_shop()
    c = SmartClient()

    # method not allowed
    response = c.post(INSTALLMENTS_PATH)
    assert response.status_code == 405

    # missing parameters
    response = c.get(INSTALLMENTS_PATH)
    assert response.status_code == 400

    # no CieloConfig for shop
    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    assert response.status_code == 400

    CieloConfig.objects.create(shop=shop)

    # basket not valid (no products and not payment/shipping methods)
    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    assert response.status_code == 400

    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')

    # configures the user basket
    _configure_basket(c)

    # only 1 installment, because no configurations were set on CieloConfig
    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    assert response.status_code == 200

    # should be the order total
    order_total = PRODUCT_QTNTY * PRODUCT_PRICE
    total_price_str = "{0}".format(format_money(shop.create_price(order_total)))

    json_content = json.loads(response.content.decode("utf-8"))
    assert len(json_content['installments']) == 1
    assert json_content['installments'][0]['number'] == 1
    assert total_price_str in json_content['installments'][0]['name']


@pytest.mark.django_db
def test_get_installments_3x_no_intereset():
    """
        Max 3 installs with no intereset
    """
    shop = get_default_shop()
    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')
    c = SmartClient()
    _configure_basket(c)
    CieloConfig.objects.create(shop=shop,
                               max_installments=3,
                               installments_without_interest=3)

    order_total = PRODUCT_QTNTY * PRODUCT_PRICE
    total_price_str = "{0}".format(format_money(shop.create_price(order_total)))

    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    json_content = json.loads(response.content.decode("utf-8"))
    assert len(json_content['installments']) == 3

    assert json_content['installments'][0]['number'] == 1
    assert total_price_str in json_content['installments'][0]['name']

    total_2x_no_interest = format_money(shop.create_price(order_total / Decimal(2)))
    assert json_content['installments'][1]['number'] == 2
    assert total_price_str in json_content['installments'][1]['name']
    assert total_2x_no_interest in json_content['installments'][1]['name']

    total_3x_no_interest = format_money(shop.create_price(order_total / Decimal(3)))
    assert json_content['installments'][2]['number'] == 3
    assert total_price_str in json_content['installments'][2]['name']
    assert total_3x_no_interest in json_content['installments'][2]['name']


@pytest.mark.django_db
def test_get_installments_9x_with_simples_intereset():
    """
        Max 9 installs with SIMPLE intereset
        interest_rate = 4.00%
    """
    shop = get_default_shop()
    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')
    c = SmartClient()
    _configure_basket(c)
    cielo_config = CieloConfig.objects.create(shop=shop,
                                              max_installments=9,
                                              installments_without_interest=3,
                                              interest_type=InterestType.Simple,
                                              interest_rate=Decimal(4.0))
    SHIP_AMOUNT = Decimal(19.0)
    shipping_method = get_default_shipping_method()
    shipping_method.behavior_components.add(
        FixedCostBehaviorComponent.objects.create(price_value=SHIP_AMOUNT)
    )

    order_total = (PRODUCT_QTNTY * PRODUCT_PRICE) + SHIP_AMOUNT
    installment_choices = InstallmentContext(order_total, cielo_config).get_intallments_choices()

    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    json_content = json.loads(response.content.decode("utf-8"))
    assert len(json_content['installments']) == len(installment_choices)

    for installment in range(len(installment_choices)):
        total = format_money(shop.create_price(installment_choices[installment][2]))
        installment_amount = format_money(shop.create_price(installment_choices[installment][1]))

        assert json_content['installments'][installment]['number'] == installment+1
        assert installment_amount in json_content['installments'][installment]['name']
        assert total in json_content['installments'][installment]['name']


@pytest.mark.django_db
def test_get_installments_12x_with_simples_intereset():
    """
        Max 12 installs with PRICE intereset
        interest_rate = 2.30%
        min_installment_amount = 30.00
    """
    shop = get_default_shop()
    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')
    c = SmartClient()
    _configure_basket(c)
    cielo_config = CieloConfig.objects.create(shop=shop,
                                              max_installments=12,
                                              installments_without_interest=2,
                                              interest_type=InterestType.Price,
                                              interest_rate=Decimal(2.3),
                                              min_installment_amount=Decimal(30))

    order_total = (PRODUCT_QTNTY * PRODUCT_PRICE)
    installment_choices = InstallmentContext(order_total, cielo_config).get_intallments_choices()

    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Visa})
    json_content = json.loads(response.content.decode("utf-8"))
    assert len(json_content['installments']) == len(installment_choices)

    for installment in range(len(installment_choices)):
        total = format_money(shop.create_price(installment_choices[installment][2]))
        installment_amount = format_money(shop.create_price(installment_choices[installment][1]))

        assert json_content['installments'][installment]['number'] == installment+1
        assert installment_amount in json_content['installments'][installment]['name']
        assert total in json_content['installments'][installment]['name']


@pytest.mark.django_db
def test_get_installments_cc_does_not_allow_installments():
    """
        Max 9 installs with SIMPLE intereset
        interest_rate = 4.00%
        Credit card does not allow installments
    """
    shop = get_default_shop()
    create_default_order_statuses()
    populate_if_required()
    set_current_theme('shuup.themes.classic_gray')
    c = SmartClient()
    _configure_basket(c)
    CieloConfig.objects.create(shop=shop,
                               max_installments=9,
                               installments_without_interest=3,
                               interest_type=InterestType.Simple,
                               interest_rate=Decimal(4.0))

    order_total = (PRODUCT_QTNTY * PRODUCT_PRICE)
    total_price_str = "{0}".format(format_money(shop.create_price(order_total)))

    response = c.get(INSTALLMENTS_PATH, {"cc_brand": CieloCardBrand.Discover})
    json_content = json.loads(response.content.decode("utf-8"))
    assert len(json_content['installments']) == 1
    assert json_content['installments'][0]['number'] == 1
    assert total_price_str in json_content['installments'][0]['name']


@pytest.mark.django_db
def test_transaction_success():
    c = _get_configured_basket_client()
    CieloConfig.objects.create(shop=get_default_shop(),
                               max_installments=10)
    data = CC_VISA_1X_INFO

    # No url-autenticacao
    transacao = get_in_progress_transaction(numero=1,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Credit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex,
                                            return_url=None)
    transacao = get_approved_transaction(transacao)
    transacao_cancelada = get_cancelled_transaction(copy.copy(transacao))

    return_url_1 = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 1})
    return_url_2 = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 2})

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            with patch.object(CieloRequest, 'cancelar', return_value=transacao_cancelada) as mock_method:

                response = c.post(TRANSACTION_PATH, data=data)
                json_content = json.loads(response.content.decode("utf-8"))
                assert json_content["success"] is True
                assert json_content["redirect_url"].endswith(return_url_1)

                t1 = CieloTransaction.objects.first()
                assert t1.status == CieloTransactionStatus.Authorized

                # request again.. the last transaction must be cancelled
                response = c.post(TRANSACTION_PATH, data=data)
                json_content = json.loads(response.content.decode("utf-8"))
                assert json_content["success"] is True
                assert json_content["redirect_url"].endswith(return_url_2)

                # deve ter invocado o método para cancelar
                assert mock_method.called

                t2 = CieloTransaction.objects.last()
                assert t2.status == CieloTransactionStatus.Authorized


@pytest.mark.django_db
def test_transaction_success_captured():
    c = _get_configured_basket_client()
    CieloConfig.objects.create(shop=get_default_shop(),
                               max_installments=10)
    data = CC_VISA_1X_INFO

    transacao1 = get_in_progress_transaction(numero=1,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Debit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao1):
        with patch.object(CieloRequest, 'consultar', return_value=transacao1):
            response = c.post(TRANSACTION_PATH, data=data)
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content["success"] is True
            assert json_content["redirect_url"].endswith(AUTH_URL)

    t1 = CieloTransaction.objects.first()
    assert t1.status == CieloTransactionStatus.InProgress

    return_url = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 1})
    transacao1_capturada = get_captured_transaction(copy.copy(get_approved_transaction(transacao1)))

    with patch.object(CieloRequest, 'consultar', return_value=transacao1_capturada):
        response = c.post(return_url)
        assert response.status_code == 302
        assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "confirm"}))

    t1.refresh_from_db()
    assert t1.status == CieloTransactionStatus.Captured
    assert t1.authorization_lr == "00"

    # call again, just to be certain
    with patch.object(CieloRequest, 'consultar', return_value=transacao1_capturada):
        response = c.post(return_url)
        assert response.status_code == 302
        assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "confirm"}))
        assert "Transaction authorized" in response.cookies['messages'].value

    t1.refresh_from_db()
    assert t1.status == CieloTransactionStatus.Captured
    assert t1.authorization_lr == "00"


    # now call authorize again, this will make T1 to be cancelled
    transacao2 = get_in_progress_transaction(numero=2,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Debit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex)
    transacao2_capturada = get_captured_transaction(get_approved_transaction(copy.copy(transacao2)))

    transacao1_cancelada = get_cancelled_transaction(transacao1)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao2):
        with patch.object(CieloRequest, 'consultar', return_value=transacao2):
            with patch.object(CieloRequest, 'cancelar', return_value=transacao1_cancelada) as mocked_method:
                response = c.post(TRANSACTION_PATH, data=data)
                json_content = json.loads(response.content.decode("utf-8"))
                assert json_content["success"] is True
                assert json_content["redirect_url"].endswith(AUTH_URL)
                
                # cancelar must be called
                assert mocked_method.called

    t2 = CieloTransaction.objects.last()
    assert t2.status == CieloTransactionStatus.InProgress
    return_url_2 = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 2})

    with patch.object(CieloRequest, 'consultar', return_value=transacao2_capturada):
        response = c.post(return_url_2)
        assert response.status_code == 302
        assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "confirm"}))

    t2.refresh_from_db()
    assert t2.status == CieloTransactionStatus.Captured


@pytest.mark.django_db
def test_transaction_not_authorized():
    c = _get_configured_basket_client()
    CieloConfig.objects.create(shop=get_default_shop(),
                               max_installments=10)
    data = CC_VISA_1X_INFO

    # No url-autenticacao
    transacao = get_in_progress_transaction(numero=1,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Credit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex,
                                            return_url=None)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
                response = c.post(TRANSACTION_PATH, data=data)
                json_content = json.loads(response.content.decode("utf-8"))
                assert json_content["success"] is False
                assert len(json_content["error"]) > 0

                t1 = CieloTransaction.objects.first()
                assert t1.status == CieloTransactionStatus.InProgress


@pytest.mark.django_db
def test_return_view_not_authorized():
    c = _get_configured_basket_client()
    CieloConfig.objects.create(shop=get_default_shop(),
                               max_installments=10)
    data = CC_VISA_1X_INFO

    transacao1 = get_in_progress_transaction(numero=1,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Debit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao1):
        with patch.object(CieloRequest, 'consultar', return_value=transacao1):
            response = c.post(TRANSACTION_PATH, data=data)
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content["success"] is True
            assert json_content["redirect_url"].endswith(AUTH_URL)

    t1 = CieloTransaction.objects.first()
    assert t1.status == CieloTransactionStatus.InProgress

    return_url = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 1})

    transacao1_authenticating = copy.copy(transacao1)
    transacao1_authenticating.status = CieloTransactionStatus.Authenticating

    # the transaction is authenticating for a long time, cancel it and return to payment
    with patch.object(CieloRequest, 'consultar', return_value=transacao1_authenticating):
        response = c.post(return_url)
        assert response.status_code == 302
        assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "payment"}))
        assert "Transaction not authorized:" in response.cookies['messages'].value

    t1.refresh_from_db()
    assert t1.status == CieloTransactionStatus.Authenticating
    assert t1.authorization_lr == ""


@pytest.mark.django_db
def test_return_view_not_identified():
    c = _get_configured_basket_client()
    CieloConfig.objects.create(shop=get_default_shop(),
                               max_installments=10)
    data = CC_VISA_1X_INFO

    # it does not exist yeat
    return_url = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 1})
    response = c.post(return_url)
    assert response.status_code == 302
    assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "payment"}))
    assert "Payment not identified. Old transactions were also cancelled" in response.cookies['messages'].value

    transacao1 = get_in_progress_transaction(numero=1,
                                            valor=Decimal(PRODUCT_PRICE * PRODUCT_QTNTY),
                                            produto=CieloProduct.Debit,
                                            bandeira=CC_VISA_1X_INFO['cc_brand'],
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=uuid.uuid4().hex)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao1):
        with patch.object(CieloRequest, 'consultar', return_value=transacao1):
            response = c.post(TRANSACTION_PATH, data=data)
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content["success"] is True
            assert json_content["redirect_url"].endswith(AUTH_URL)

    t1 = CieloTransaction.objects.first()
    assert t1.status == CieloTransactionStatus.InProgress

    # transaction exists, but wrong cielo_order_pk
    return_url = reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": 45405})
    transacao1_cancelada = get_cancelled_transaction(transacao1)

    with patch.object(CieloRequest, 'cancelar', return_value=transacao1_cancelada):
        response = c.post(return_url)
        assert response.status_code == 302
        assert response.url.endswith(reverse("shuup:checkout", kwargs={"phase": "payment"}))
        assert "Payment not identified. Old transactions were also cancelled" in response.cookies['messages'].value

    t1.refresh_from_db()
    assert t1.status == CieloTransactionStatus.Cancelled
