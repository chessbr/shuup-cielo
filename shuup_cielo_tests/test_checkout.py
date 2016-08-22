# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

from decimal import Decimal
import json
import uuid

from django.core.urlresolvers import reverse
import iso8601
from mock import patch
import pytest

from cielo_webservice.request import CieloRequest
from shuup.core.defaults.order_statuses import create_default_order_statuses
from shuup.core.models._orders import Order, OrderStatus, PaymentStatus
from shuup.core.models._product_shops import ShopProduct
from shuup.testing.factories import (
    _get_service_provider, get_default_product, get_default_shipping_method, get_default_shop,
    get_default_supplier, get_default_tax_class
)
from shuup.testing.mock_population import populate_if_required
from shuup.testing.soup_utils import extract_form_fields
from shuup.xtheme._theme import set_current_theme
from shuup_cielo.constants import (
    CIELO_SERVICE_CREDIT, CieloCardBrand, CieloProduct, CieloTransactionStatus
)
from shuup_cielo.models import (
    CieloConfig, CieloOrderTransaction, CieloPaymentProcessor, CieloTransaction, InstallmentContext
)
from shuup_cielo.objects import CIELO_ORDER_TRANSACTION_ID_KEY, CIELO_TRANSACTION_ID_KEY
from shuup_cielo.utils import decimal_to_int_cents
from shuup_cielo_tests import (
    AUTH_URL, CC_VISA_1X_INFO, CC_VISA_4X_INFO, get_approved_transaction, get_captured_transaction,
    get_in_progress_transaction, PRODUCT_PRICE
)
from shuup_tests.front.test_checkout_flow import fill_address_inputs
from shuup_tests.utils import SmartClient


def get_payment_provider(**kwargs):
    return _get_service_provider(CieloPaymentProcessor)

def get_cielo_config(**kwargs):
    return CieloConfig.objects.get_or_create(shop=get_default_shop(), **kwargs)[0]

def initialize():
    get_default_shop()
    get_cielo_config()
    set_current_theme('shuup.themes.classic_gray')
    create_default_order_statuses()
    populate_if_required()

    default_product = get_default_product()
    sp = ShopProduct.objects.get(product=default_product, shop=get_default_shop())
    sp.default_price = get_default_shop().create_price(PRODUCT_PRICE)
    sp.save()


@pytest.mark.django_db
def test_order_flow_with_payment_phase_credit_card_success():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Com URL para autenticação
            - 1 parcela sem juros
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()
    ORDER_TOTAL = PRODUCT_PRICE * 1

    basket_path = reverse("shuup:basket")
    add_to_basket_resp = c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })
    assert add_to_basket_resp.status_code < 400


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
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})
    transaction_path = reverse("shuup:cielo_make_transaction")


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    response = c.post(addresses_path, data=inputs)
    assert response.status_code == 302, "Address phase should redirect forth"
    assert response.url.endswith(methods_path)

    # Phase: Methods
    assert Order.objects.filter(payment_method=payment_method).count() == 0
    response = c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    assert response.status_code == 302, "Methods phase should redirect forth"
    assert response.url.endswith(confirm_path)
    response = c.get(confirm_path)
    assert response.status_code == 302, "Confirm should first redirect forth"
    assert response.url.endswith(payment_path)

    tid = uuid.uuid4().hex

    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # Phase: Payment
            response = c.soup(payment_path)
            response = c.post(transaction_path, CC_VISA_1X_INFO)

            assert response.status_code == 200
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content['redirect_url'] == AUTH_URL

            cielo_transaction = CieloTransaction.objects.get(tid=tid)
            assert cielo_transaction.status == CieloTransactionStatus.InProgress
            assert cielo_transaction.cc_brand == CC_VISA_1X_INFO['cc_brand']
            assert cielo_transaction.cc_holder == CC_VISA_1X_INFO['cc_holder']
            assert cielo_transaction.installments == CC_VISA_1X_INFO['installments']
            assert cielo_transaction.cc_product == CieloProduct.Credit
            assert abs(cielo_transaction.total_value - ORDER_TOTAL) < 0.01
            assert cielo_transaction.status.value == transacao.status

    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'consultar', return_value=transacao):
        # Phase: Confirm Order
        assert Order.objects.count() == 0
        confirm_soup = c.soup(confirm_path)
        response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
        assert response.status_code == 302, "Confirm should redirect forth"
        assert Order.objects.count() == 1

        order = Order.objects.filter(payment_method=payment_method).first()
        process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
        process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
        order_complete_path = reverse("shuup:order_complete",kwargs={"pk": order.pk, "key": order.key})

        # Visit payment page
        response = c.get(process_payment_path)
        assert response.status_code == 302, "Payment page should redirect forth"
        assert response.url.endswith(process_payment_return_path)

        # Check payment return
        response = c.get(process_payment_return_path)
        assert response.status_code == 302, "Payment return should redirect forth"
        assert response.url.endswith(order_complete_path)

        cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order, tid=tid)
        assert cielo_transaction.status == CieloTransactionStatus.Authorized
        assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
        assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
        assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

        assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
        assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

        assert cielo_transaction.total_captured.value == Decimal()
        assert cielo_transaction.total_reversed.value == Decimal()

    order.refresh_from_db()
    assert order.payment_data.get(CIELO_TRANSACTION_ID_KEY)
    assert order.payment_data.get(CIELO_ORDER_TRANSACTION_ID_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID



@pytest.mark.django_db
def test_credit_card_success_2():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Sem URL para autenticação
            - 4 parcelas
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    add_to_basket_resp = c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })
    assert add_to_basket_resp.status_code < 400

    ORDER_TOTAL = PRODUCT_PRICE * 10

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()
    assert isinstance(processor, CieloPaymentProcessor)

    # aumenta o limite máximo de parcelas para 4
    cielo_config = get_cielo_config()
    cielo_config.max_installments = 4
    cielo_config.save()

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    transaction_path = reverse("shuup:cielo_make_transaction")
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    response = c.post(addresses_path, data=inputs)
    assert response.status_code == 302, "Address phase should redirect forth"
    assert response.url.endswith(methods_path)

    # Phase: Methods
    assert Order.objects.filter(payment_method=payment_method).count() == 0
    response = c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    assert response.status_code == 302, "Methods phase should redirect forth"
    assert response.url.endswith(confirm_path)
    response = c.get(confirm_path)
    assert response.status_code == 302, "Confirm should first redirect forth"
    assert response.url.endswith(payment_path)

    tid = uuid.uuid4().hex
    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid,
                                            return_url=None)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # Phase: pay
            response = c.soup(payment_path)
            response = c.post(transaction_path, CC_VISA_4X_INFO)

            assert response.status_code == 200
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content['redirect_url'].endswith(reverse("shuup:cielo_transaction_return",
                                                                 kwargs={"cielo_order_pk": 1}))

            cielo_transaction = CieloTransaction.objects.get(tid=tid)
            "{0}".format(cielo_transaction) # just to test __str__
            assert cielo_transaction.cc_brand == CC_VISA_4X_INFO['cc_brand']
            assert cielo_transaction.cc_holder == CC_VISA_4X_INFO['cc_holder']
            assert cielo_transaction.installments == CC_VISA_4X_INFO['installments']
            assert cielo_transaction.cc_product == CieloProduct.InstallmentCredit
            assert abs(cielo_transaction.total_value - ORDER_TOTAL) < 0.01
            assert cielo_transaction.status.value == transacao.status

            response = c.post(json_content['redirect_url'])
            assert response.status_code == 302
            assert response.url.endswith(confirm_path)

            # Phase: Confirm
            assert Order.objects.count() == 0
            confirm_soup = c.soup(confirm_path)
            response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
            assert response.status_code == 302, "Confirm should redirect forth"

            order = Order.objects.filter(payment_method=payment_method).first()
            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
            process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
            order_complete_path = reverse("shuup:order_complete",kwargs={"pk": order.pk, "key": order.key})

            response = c.get(process_payment_path)
            assert response.status_code == 302, "Payment page should redirect forth"
            assert response.url.endswith(process_payment_return_path)

            # Check payment return
            response = c.get(process_payment_return_path)
            assert response.status_code == 302, "Payment return should redirect forth"
            assert response.url.endswith(order_complete_path)

            cielo_order_transaction = CieloOrderTransaction.objects.filter(order=order).first()
            "{0}".format(cielo_order_transaction) # just to test __str__

            cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order, tid=tid)
            assert cielo_transaction.status == CieloTransactionStatus.Authorized
            assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
            assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
            assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

            assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
            assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

            assert cielo_transaction.total_captured.value == Decimal()
            assert cielo_transaction.total_reversed.value == Decimal()

    order.refresh_from_db()
    assert order.payment_data.get(CIELO_TRANSACTION_ID_KEY)
    assert order.payment_data.get(CIELO_ORDER_TRANSACTION_ID_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID


@pytest.mark.django_db
def test_credit_card_success_3():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Sem URL para autenticação
            - 4 parcelas com juros
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })

    ORDER_TOTAL = PRODUCT_PRICE * 10

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

    # aumenta o limite máximo de parcelas para 4
    cielo_config = get_cielo_config()
    cielo_config.max_installments = 4
    cielo_config.installments_without_interest = 1
    cielo_config.interest_rate = Decimal(3.20)
    cielo_config.save()

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    transaction_path = reverse("shuup:cielo_make_transaction")
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})

    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)
    c.post(methods_path,data={"payment_method": payment_method.pk,"shipping_method": shipping_method.pk})
    c.get(confirm_path)

    tid = uuid.uuid4().hex
    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid,
                                            return_url=None)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # Phase: pay
            c.soup(payment_path)
            response = c.post(transaction_path, CC_VISA_4X_INFO)

            assert response.status_code == 200
            json_content = json.loads(response.content.decode("utf-8"))
            assert json_content['redirect_url'].endswith(reverse("shuup:cielo_transaction_return",
                                                                 kwargs={"cielo_order_pk": 1}))

            choices = InstallmentContext(ORDER_TOTAL, cielo_config).get_intallments_choices()

            cielo_transaction = CieloTransaction.objects.get(tid=tid)
            assert cielo_transaction.cc_product == CieloProduct.InstallmentCredit
            assert abs(cielo_transaction.total_value - choices[3][2]) <= Decimal(0.01)
            assert cielo_transaction.status.value == transacao.status

            response = c.post(json_content['redirect_url'])
            confirm_soup = c.soup(confirm_path)
            response = c.post(confirm_path, data=extract_form_fields(confirm_soup))

            order = Order.objects.filter(payment_method=payment_method).first()
            assert abs(order.taxful_total_price.value - choices[3][2]) <= Decimal(0.01)

            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
            process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
            response = c.get(process_payment_path)

            response = c.get(process_payment_return_path)
            cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order, tid=tid)

    order.refresh_from_db()
    assert order.payment_data.get(CIELO_TRANSACTION_ID_KEY)
    assert order.payment_data.get(CIELO_ORDER_TRANSACTION_ID_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID


@pytest.mark.django_db
def test_credit_card_fail():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Sem URL para autenticação
            - 4 parcelas
            - dados do pagamento nao existem
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })

    ORDER_TOTAL = PRODUCT_PRICE * 10

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

    # aumenta o limite máximo de parcelas para 4
    cielo_config = get_cielo_config()
    cielo_config.max_installments = 4
    cielo_config.save()

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class()
    )

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    transaction_path = reverse("shuup:cielo_make_transaction")
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})

    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)
    c.post(methods_path, data={"payment_method": payment_method.pk, "shipping_method": shipping_method.pk})
    c.get(confirm_path)

    tid = uuid.uuid4().hex
    transacao = get_in_progress_transaction(1,
                                         decimal_to_int_cents(ORDER_TOTAL),
                                         CieloProduct.InstallmentCredit,
                                         CieloCardBrand.Visa,
                                         CC_VISA_4X_INFO['installments'],
                                         tid,
                                         return_url=None)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # Phase: pay
            c.soup(payment_path)
            response = c.post(transaction_path, CC_VISA_4X_INFO)

            json_content = json.loads(response.content.decode("utf-8"))
            response = c.post(json_content['redirect_url'])
            confirm_soup = c.soup(confirm_path)

            response = c.post(confirm_path, data=extract_form_fields(confirm_soup))

            order = Order.objects.filter(payment_method=payment_method).first()
            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})

            # FORCE CLEAR ORDER PAYMENT DATA
            order.payment_data = {}
            order.save()

            response = c.get(process_payment_path)

            order.refresh_from_db()
            assert order.status == OrderStatus.objects.get_default_canceled()


@pytest.mark.django_db
def test_credit_card_fail2():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Sem URL para autenticação
            - 4 parcelas
            - valor total do parcelado diferente do total do pedido
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })

    ORDER_TOTAL = PRODUCT_PRICE * 10

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

    # aumenta o limite máximo de parcelas para 4
    cielo_config = get_cielo_config()
    cielo_config.max_installments = 4
    cielo_config.save()

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class()
    )

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    transaction_path = reverse("shuup:cielo_make_transaction")
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})

    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)
    c.post(methods_path, data={"payment_method": payment_method.pk, "shipping_method": shipping_method.pk})
    c.get(confirm_path)

    tid = uuid.uuid4().hex
    transacao = get_in_progress_transaction(1,
                                         decimal_to_int_cents(ORDER_TOTAL),
                                         CieloProduct.InstallmentCredit,
                                         CieloCardBrand.Visa,
                                         CC_VISA_4X_INFO['installments'],
                                         tid,
                                         return_url=None)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # Phase: pay
            c.soup(payment_path)
            response = c.post(transaction_path, CC_VISA_4X_INFO)

            json_content = json.loads(response.content.decode("utf-8"))
            response = c.post(json_content['redirect_url'])

            # ok, no redirect
            response = c.get(confirm_path)
            assert response.status_code == 200

            # sabotagem: adiciona um item ao carrinho
            c.post(basket_path, data={
                "command": "add",
                "product_id": default_product.pk,
                "quantity": 10,
                "supplier": get_default_supplier().pk
            })

            # again, now with redirect
            response = c.get(confirm_path)
            assert response.status_code == 302
            assert response.url.endswith(payment_path)


@pytest.mark.django_db
def test_debit_auto_capture_with_auth():
    """
        Caso:
            - Transação com Cartão de Débito
            - Auto captura HABILITADO
            - Com URL para autenticação
            - 1 parcela
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    add_to_basket_resp = c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })
    assert add_to_basket_resp.status_code < 400

    ORDER_TOTAL = PRODUCT_PRICE * 10

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()
    assert isinstance(processor, CieloPaymentProcessor)

    # aumenta o limite máximo de parcelas para 4
    cielo_config = get_cielo_config()
    cielo_config.max_installments = 4
    cielo_config.save()

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shuup:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shuup:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shuup:checkout", kwargs={"phase": "payment"})
    transaction_path = reverse("shuup:cielo_make_transaction")
    confirm_path = reverse("shuup:checkout", kwargs={"phase": "confirm"})


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    response = c.post(addresses_path, data=inputs)
    assert response.status_code == 302, "Address phase should redirect forth"
    assert response.url.endswith(methods_path)

    # Phase: Methods
    assert Order.objects.filter(payment_method=payment_method).count() == 0
    response = c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    assert response.status_code == 302, "Methods phase should redirect forth"
    assert response.url.endswith(confirm_path)
    response = c.get(confirm_path)
    assert response.status_code == 302, "Confirm should first redirect forth"
    assert response.url.endswith(payment_path)

    tid = uuid.uuid4().hex

    transacao = get_in_progress_transaction(1,
                                         decimal_to_int_cents(ORDER_TOTAL),
                                         CieloProduct.InstallmentCredit,
                                         CieloCardBrand.Visa,
                                         CC_VISA_4X_INFO['installments'],
                                         tid,
                                         return_url=None)
    transacao = get_approved_transaction(transacao)
    transacao = get_captured_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            with patch.object(CieloRequest, 'capturar', return_value=transacao):
                # Phase: pay
                response = c.soup(payment_path)
                response = c.post(transaction_path, CC_VISA_4X_INFO)

                assert response.status_code == 200
                json_content = json.loads(response.content.decode("utf-8"))
                assert json_content['redirect_url'].endswith(reverse("shuup:cielo_transaction_return",
                                                                     kwargs={"cielo_order_pk": 1}))

                cielo_transaction = CieloTransaction.objects.get(tid=tid)
                assert cielo_transaction.cc_brand == CC_VISA_4X_INFO['cc_brand']
                assert cielo_transaction.cc_holder == CC_VISA_4X_INFO['cc_holder']
                assert cielo_transaction.installments == CC_VISA_4X_INFO['installments']
                assert cielo_transaction.cc_product == CieloProduct.InstallmentCredit
                assert abs(cielo_transaction.total_value - ORDER_TOTAL) < 0.01
                assert cielo_transaction.status.value == transacao.status

                response = c.post(json_content['redirect_url'])
                assert response.status_code == 302
                assert response.url.endswith(confirm_path)

                # Phase: Confirm
                assert Order.objects.count() == 0
                confirm_soup = c.soup(confirm_path)
                response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
                assert response.status_code == 302, "Confirm should redirect forth"

                order = Order.objects.filter(payment_method=payment_method).first()
                process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
                process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
                order_complete_path = reverse("shuup:order_complete",kwargs={"pk": order.pk, "key": order.key})

                response = c.get(process_payment_path)
                assert response.status_code == 302, "Payment page should redirect forth"
                assert response.url.endswith(process_payment_return_path)

                # Check payment return
                response = c.get(process_payment_return_path)
                assert response.status_code == 302, "Payment return should redirect forth"
                assert response.url.endswith(order_complete_path)

                cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order, tid=tid)
                assert cielo_transaction.status == CieloTransactionStatus.Captured

                assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
                assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
                assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

                assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
                assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

                assert cielo_transaction.total_captured_value == ORDER_TOTAL
                assert cielo_transaction.total_reversed_value == Decimal()

    order.refresh_from_db()
    assert order.payment_data.get(CIELO_TRANSACTION_ID_KEY)
    assert order.payment_data.get(CIELO_ORDER_TRANSACTION_ID_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID
