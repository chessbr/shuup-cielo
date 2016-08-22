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
import uuid

from django.core.urlresolvers import reverse
from mock import patch
import pytest

from cielo_webservice.request import CieloRequest
from shuup.core.defaults.order_statuses import create_default_order_statuses
from shuup.core.models._orders import Order
from shuup.core.models._product_shops import ShopProduct
from shuup.testing.factories import (
    get_default_product, get_default_shipping_method, get_default_shop, get_default_supplier,
    get_default_tax_class
)
from shuup.testing.mock_population import populate_if_required
from shuup.testing.soup_utils import extract_form_fields
from shuup.testing.utils import apply_request_middleware
from shuup.utils.importing import load
from shuup.xtheme._theme import set_current_theme
from shuup_cielo.admin.forms import (
    CieloConfigForm, CieloPaymentProcessorForm, DiscountPercentageBehaviorComponentForm
)
from shuup_cielo.constants import (
    CIELO_SERVICE_CREDIT, CieloCardBrand, CieloProduct, CieloTransactionStatus
)
from shuup_cielo.models import CieloTransaction
from shuup_cielo.utils import decimal_to_int_cents
from shuup_cielo_tests import (
    CC_VISA_1X_INFO, get_approved_transaction, get_cancelled_transaction, get_captured_transaction,
    get_in_progress_transaction, PRODUCT_PRICE
)
from shuup_cielo_tests.test_checkout import get_cielo_config, get_payment_provider
from shuup_tests.front.test_checkout_flow import fill_address_inputs
from shuup_tests.utils import SmartClient


def initialize():
    get_cielo_config()
    get_default_shop()
    set_current_theme('shuup.themes.classic_gray')
    create_default_order_statuses()
    populate_if_required()

    default_product = get_default_product()
    sp = ShopProduct.objects.get(product=default_product, shop=get_default_shop())
    sp.default_price = get_default_shop().create_price(PRODUCT_PRICE)
    sp.save()

@pytest.mark.django_db
def test_refresh_transaction_view(rf, admin_user):
    initialize()

    c = SmartClient()
    default_product = get_default_product()
    ORDER_TOTAL = PRODUCT_PRICE * 1

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

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
    c.post(addresses_path, data=inputs)
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    tid = uuid.uuid4().hex

    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.soup(payment_path)
            c.post(transaction_path, CC_VISA_1X_INFO)
            confirm_soup = c.soup(confirm_path)
            c.post(confirm_path, data=extract_form_fields(confirm_soup))
            order = Order.objects.filter(payment_method=payment_method).first()
            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
            process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
            c.get(process_payment_path)
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order)

    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()

    view = load("shuup_cielo.admin.views.RefreshTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)

    # request sem parametro - bad request
    response = view(request)
    assert response.status_code == 500

    transacao = get_captured_transaction(transacao)
    with patch.object(CieloRequest, 'consultar', return_value=transacao):
        request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk}), user=admin_user)
        response = view(request)
        assert response.status_code == 200
        cielo_transaction.refresh_from_db()
        assert cielo_transaction.total_captured_value == order.taxful_total_price_value


@pytest.mark.parametrize("with_amount", [True, False])
@pytest.mark.django_db
def test_capture_transaction_view(rf, admin_user, with_amount):
    initialize()

    c = SmartClient()
    default_product = get_default_product()
    ORDER_TOTAL = PRODUCT_PRICE * 1

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

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
    c.post(addresses_path, data=inputs)
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    tid = uuid.uuid4().hex

    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.soup(payment_path)
            c.post(transaction_path, CC_VISA_1X_INFO)
            confirm_soup = c.soup(confirm_path)
            c.post(confirm_path, data=extract_form_fields(confirm_soup))
            order = Order.objects.filter(payment_method=payment_method).first()
            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
            process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
            c.get(process_payment_path)
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order)

    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()


    view = load("shuup_cielo.admin.views.CaptureTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)

    # request sem parametros - bad request
    response = view(request)
    assert response.status_code == 500

    transacao = get_captured_transaction(transacao)

    with patch.object(CieloRequest, 'consultar', return_value=transacao):
        with patch.object(CieloRequest, 'capturar', return_value=transacao):
            if with_amount:
                request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk,
                                                                 "amount":order.taxful_total_price_value}), user=admin_user)
            else:
                request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk}), user=admin_user)

            response = view(request)
            assert response.status_code == 200
            cielo_transaction.refresh_from_db()
            assert cielo_transaction.total_captured.value == order.taxful_total_price_value
            assert cielo_transaction.status.value == CieloTransactionStatus.Captured.value

    view = load("shuup.admin.modules.orders.views.OrderEditView").as_view()
    request = apply_request_middleware(rf.get("/", {"id":order.pk}), user=admin_user)
    response = view(request)
    assert response.status_code == 200


@pytest.mark.parametrize("with_amount", [True, False])
@pytest.mark.django_db
def test_cancel_transaction_view(rf, admin_user, with_amount):
    ''' Cancela transacao informando valor '''
    initialize()

    c = SmartClient()
    default_product = get_default_product()
    ORDER_TOTAL = PRODUCT_PRICE * 1

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()

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
    c.post(addresses_path, data=inputs)
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    tid = uuid.uuid4().hex

    transacao = get_in_progress_transaction(numero=1,
                                            valor=decimal_to_int_cents(ORDER_TOTAL),
                                            produto=CieloProduct.Credit,
                                            bandeira=CieloCardBrand.Visa,
                                            parcelas=CC_VISA_1X_INFO['installments'],
                                            tid=tid)
    transacao = get_approved_transaction(transacao)

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.soup(payment_path)
            c.post(transaction_path, CC_VISA_1X_INFO)
            confirm_soup = c.soup(confirm_path)
            c.post(confirm_path, data=extract_form_fields(confirm_soup))
            order = Order.objects.filter(payment_method=payment_method).first()
            process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
            process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
            c.get(process_payment_path)
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = CieloTransaction.objects.get(order_transaction__order=order)

    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()

    view = load("shuup_cielo.admin.views.CancelTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)

    # request sem parametros - bad request
    response = view(request)
    assert response.status_code == 500

    transacao = get_cancelled_transaction(transacao)

    with patch.object(CieloRequest, 'consultar', return_value=transacao):
        with patch.object(CieloRequest, 'cancelar', return_value=transacao):

            if with_amount:
                request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk,
                                                                 "amount":order.taxful_total_price_value}), user=admin_user)
            else:
                request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk}), user=admin_user)

            response = view(request)
            assert response.status_code == 200
            cielo_transaction.refresh_from_db()
            assert cielo_transaction.total_reversed.value == order.taxful_total_price_value
            assert cielo_transaction.status.value == CieloTransactionStatus.Cancelled.value


def test_forms():
    CieloPaymentProcessorForm()
    DiscountPercentageBehaviorComponentForm()
    CieloConfigForm()
