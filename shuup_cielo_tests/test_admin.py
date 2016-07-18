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

from mock import patch
import pytest

from shuup_cielo.constants import (
    CIELO_SERVICE_CREDIT, CieloCardBrand, CieloProduct, CieloTransactionStatus
)
from shuup_cielo.utils import decimal_to_int_cents
from shuup_cielo_tests.test_checkout import get_payment_provider
from shuup_tests.front.test_checkout_flow import fill_address_inputs
from shuup_tests.utils import SmartClient

from django.core.urlresolvers import reverse
from django.utils.timezone import now

from cielo_webservice.models import (
    dict_to_autenticacao, dict_to_autorizacao, dict_to_cancelamento, dict_to_captura,
    dict_to_pagamento, dict_to_pedido, Transacao
)
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

# TODO:
# Testar RefreshTransactionView
# Testar CaptureTransactionView
# Testar CancelTransactionView

PRODUCT_PRICE = 19.00

def initialize():
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

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 2,
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


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)

    # Phase: Methods
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    # Phase: Cielo
    c.soup(payment_path)
    c.post(payment_path, data={"cc_number": '5453010000066167',
                               "cc_brand": CieloCardBrand.Mastercard,
                               "cc_holder": "Joao de souza",
                               "cc_valid_year": now().year+1,
                               "cc_valid_month": "%02d" % now().month,
                               "cc_security_code": "123",
                               "installments": '1'})

    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))

    order = Order.objects.filter(payment_method=payment_method).first()

    process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Mastercard,
                                     'produto':CieloProduct.Debit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.InProgress.value,
        url_autenticacao='http://CUSTUM_URL',
    )

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        c.get(process_payment_path)

    transacao.status = CieloTransactionStatus.Authorized.value
    transacao.autenticacao = dict_to_autenticacao({'codigo':'13123',
                                                 'mensagem':'autorizado',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'eci':2})
    transacao.autorizacao = dict_to_autorizacao({'codigo':'31321',
                                                 'mensagem':'autenticar',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'lr':0,
                                                 'nsu':'123'
                                               })

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = order.cielows15_transactions.all().first()
    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()

    view = load("shuup_cielo.admin.views.RefreshTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)
    
    # request sem parametro - bad request
    response = view(request)
    assert response.status_code == 500

    # simula que a transacao foi capturada e o valor foi alterado no banco de dados
    transacao.status = CieloTransactionStatus.Captured.value
    transacao.captura = dict_to_captura({'codigo':'1312',
                                     'mensagem':'capturado',
                                     'data-hora':'2016-01-01T01:00Z',
                                     'valor':decimal_to_int_cents(order.taxful_total_price_value)})
    
    with patch.object(CieloRequest, 'consultar', return_value=transacao):
        request = apply_request_middleware(rf.post("/", {"id":cielo_transaction.pk}), user=admin_user)
        response = view(request)
        assert response.status_code == 200
        cielo_transaction.refresh_from_db()
        assert cielo_transaction.total_captured.value == order.taxful_total_price_value


@pytest.mark.parametrize("with_amount", [True, False])
@pytest.mark.django_db
def test_capture_transaction_view(rf, admin_user, with_amount):
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 2,
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


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)

    # Phase: Methods
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    # Phase: Cielo
    c.soup(payment_path)
    c.post(payment_path, data={"cc_number": '5453010000066167',
                               "cc_brand": CieloCardBrand.Mastercard,
                               "cc_holder": "Joao de souza",
                               "cc_valid_year": now().year+1,
                               "cc_valid_month": "%02d" % now().month,
                               "cc_security_code": "123",
                               "installments": '1'})

    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))

    order = Order.objects.filter(payment_method=payment_method).first()

    process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Mastercard,
                                     'produto':CieloProduct.Debit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.InProgress.value,
        url_autenticacao='http://CUSTUM_URL',
    )

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        c.get(process_payment_path)

    transacao.status = CieloTransactionStatus.Authorized.value
    transacao.autenticacao = dict_to_autenticacao({'codigo':'13123',
                                                 'mensagem':'autorizado',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'eci':2})
    transacao.autorizacao = dict_to_autorizacao({'codigo':'31321',
                                                 'mensagem':'autenticar',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'lr':0,
                                                 'nsu':'123'
                                               })

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = order.cielows15_transactions.all().first()
    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()

    view = load("shuup_cielo.admin.views.CaptureTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)
    
    # request sem parametros - bad request
    response = view(request)
    assert response.status_code == 500

    # simula que a transacao foi capturada e o valor foi alterado no banco de dados
    transacao.status = CieloTransactionStatus.Captured.value
    transacao.captura = dict_to_captura({'codigo':'1312',
                                         'mensagem':'capturado',
                                         'data-hora':'2016-01-01T01:00Z',
                                         'valor':decimal_to_int_cents(order.taxful_total_price_value)})

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


@pytest.mark.parametrize("with_amount", [True, False])
@pytest.mark.django_db
def test_cancel_transaction_view(rf, admin_user, with_amount):
    ''' Cancela transacao informando valor '''
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shuup:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 2,
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


    # Phase: Addresses
    addresses_soup = c.soup(addresses_path)
    inputs = fill_address_inputs(addresses_soup, with_company=False)
    c.post(addresses_path, data=inputs)

    # Phase: Methods
    c.post(
        methods_path,
        data={
            "payment_method": payment_method.pk,
            "shipping_method": shipping_method.pk
        }
    )

    c.get(confirm_path)

    # Phase: Cielo
    c.soup(payment_path)
    c.post(payment_path, data={"cc_number": '5453010000066167',
                               "cc_brand": CieloCardBrand.Mastercard,
                               "cc_holder": "Joao de souza",
                               "cc_valid_year": now().year+1,
                               "cc_valid_month": "%02d" % now().month,
                               "cc_security_code": "123",
                               "installments": '1'})

    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))

    order = Order.objects.filter(payment_method=payment_method).first()

    process_payment_path = reverse("shuup:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shuup:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Mastercard,
                                     'produto':CieloProduct.Debit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.InProgress.value,
        url_autenticacao='http://CUSTUM_URL',
    )

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        c.get(process_payment_path)

    transacao.status = CieloTransactionStatus.Authorized.value
    transacao.autenticacao = dict_to_autenticacao({'codigo':'13123',
                                                 'mensagem':'autorizado',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'eci':2})
    transacao.autorizacao = dict_to_autorizacao({'codigo':'31321',
                                                 'mensagem':'autenticar',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':decimal_to_int_cents(order.taxful_total_price_value),
                                                 'lr':0,
                                                 'nsu':'123'
                                               })

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.get(process_payment_return_path)

    order.refresh_from_db()
    cielo_transaction = order.cielows15_transactions.all().first()
    # transacao nao capturada
    assert cielo_transaction.tid == tid
    assert cielo_transaction.total_captured.value == Decimal()

    view = load("shuup_cielo.admin.views.CancelTransactionView").as_view()
    request = apply_request_middleware(rf.post("/"), user=admin_user)
    
    # request sem parametros - bad request
    response = view(request)
    assert response.status_code == 500

    # simula que a transacao foi capturada e o valor foi alterado no banco de dados
    transacao.status = CieloTransactionStatus.Cancelled.value
    transacao.cancelamento = dict_to_cancelamento({'cancelamento': {'codigo':'1312',
                                                                    'mensagem':'capturado',
                                                                    'data-hora':'2016-01-01T01:00Z',
                                                                    'valor':decimal_to_int_cents(order.taxful_total_price_value)}})

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
