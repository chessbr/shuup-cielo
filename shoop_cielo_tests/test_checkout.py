# -*- coding: utf-8 -*-
# This file is part of Shoop Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from decimal import Decimal
import uuid

import iso8601
from mock import patch
import pytest

from shoop_cielo.constants import (
    CIELO_CREDIT_CARD_INFO_KEY, CIELO_DEBIT_CARD_INFO_KEY, CIELO_SERVICE_CREDIT,
    CIELO_SERVICE_DEBIT, CIELO_TID_INFO_KEY, CieloAuthorizationType, CieloCardBrand, CieloErrorMap,
    CieloProduct, CieloTransactionStatus, InterestType
, CIELO_INSTALLMENT_INFO_KEY)
from shoop_cielo.models import CieloWS15PaymentProcessor, CieloWS15Transaction
from shoop_cielo.utils import decimal_to_int_cents
from shoop_tests.front.test_checkout_flow import fill_address_inputs
from shoop_tests.utils import SmartClient

from django.core import signing
from django.core.urlresolvers import reverse
from django.utils.timezone import now

from cielo_webservice.exceptions import CieloRequestError
from cielo_webservice.models import (
    dict_to_autenticacao, dict_to_autorizacao, dict_to_captura, dict_to_pagamento, dict_to_pedido,
    Transacao
)
from cielo_webservice.request import CieloRequest

from shoop.core.defaults.order_statuses import create_default_order_statuses
from shoop.core.models._order_lines import OrderLineType
from shoop.core.models._orders import Order, OrderStatus, PaymentStatus
from shoop.core.models._product_shops import ShopProduct
from shoop.testing.factories import (
    _get_service_provider, get_default_product, get_default_shipping_method, get_default_shop,
    get_default_supplier, get_default_tax_class
)
from shoop.testing.mock_population import populate_if_required
from shoop.testing.soup_utils import extract_form_fields
from shoop.xtheme._theme import set_current_theme

PRODUCT_PRICE = Decimal(15.0)

def get_payment_provider(**kwargs):
    provider = _get_service_provider(CieloWS15PaymentProcessor)
    provider.ec_num=''
    provider.ec_key=''
    provider.auto_capture=False
    provider.authorization_mode=CieloAuthorizationType.IfAuthenticatedOrNot
    provider.max_installments=4
    provider.installments_without_interest=3
    provider.interest_type=InterestType.Simple
    provider.interest_rate=2
    provider.min_installment_amount=5
    provider.sandbox=True

    # override attributes
    for k,v in kwargs.items():
        if hasattr(provider, k):
            setattr(provider, k, v)

    provider.save()
    return provider

def initialize():
    get_default_shop()
    set_current_theme('shoop.themes.classic_gray')
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

    basket_path = reverse("shoop:basket")
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
    assert isinstance(processor, CieloWS15PaymentProcessor)

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})


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

    # Phase: Cielo
    response = c.soup(payment_path)
    response = c.post(payment_path, data={"cc_number": '4012001038443335',
                                          "cc_brand": CieloCardBrand.Visa,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '1'})

    assert response.status_code == 302, "Valid payment form should redirect forth"
    assert response.url.endswith(confirm_path)

    # Phase: Confirm
    assert Order.objects.count() == 0
    confirm_soup = c.soup(confirm_path)
    response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
    assert response.status_code == 302, "Confirm should redirect forth"

    assert Order.objects.count() == 1
    order = Order.objects.filter(payment_method=payment_method).first()
    assert order.payment_data.get(CIELO_CREDIT_CARD_INFO_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shoop:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
    order_complete_path = reverse("shoop:order_complete",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    assert response.url.endswith(process_payment_path), ("Confirm should have redirected to payment page")

    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Visa,
                                     'produto':CieloProduct.Credit,
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
        # Visit payment page
        response = c.get(process_payment_path)
        assert response.status_code == 302, "Payment page should redirect forth"
        assert response.url.endswith(transacao.url_autenticacao)

        order.refresh_from_db()
        assert order.payment_data.get(CIELO_TID_INFO_KEY) == tid

        cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
        assert cielo_transaction.cc_brand == CieloCardBrand.Visa
        assert cielo_transaction.cc_holder == 'Joao de souza'
        assert cielo_transaction.installments == 1
        assert cielo_transaction.cc_product == CieloProduct.Credit
        assert abs(cielo_transaction.total.value - order.taxful_total_price_value) < 0.01
        assert cielo_transaction.status.value == transacao.status

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
            # Check payment return
            response = c.get(process_payment_return_path)
            assert response.status_code == 302, "Payment return should redirect forth"
            assert response.url.endswith(order_complete_path)

            cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
            assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
            assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
            assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

            assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
            assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

            assert cielo_transaction.total_captured.value == Decimal()
            assert cielo_transaction.total_reversed.value == Decimal()

    order.refresh_from_db()
    assert order.payment_status == PaymentStatus.FULLY_PAID
    assert order.payment_data.get(CIELO_CREDIT_CARD_INFO_KEY) is None  # removed key


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

    basket_path = reverse("shoop:basket")
    add_to_basket_resp = c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
        "supplier": get_default_supplier().pk
    })
    assert add_to_basket_resp.status_code < 400


    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider()
    assert isinstance(processor, CieloWS15PaymentProcessor)

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})


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

    # Phase: Cielo
    response = c.soup(payment_path)
    response = c.post(payment_path, data={"cc_number": '4012001038443335',
                                          "cc_brand": CieloCardBrand.Visa,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '4'})

    assert response.status_code == 302, "Valid payment form should redirect forth"
    assert response.url.endswith(confirm_path)

    # Phase: Confirm
    assert Order.objects.count() == 0
    confirm_soup = c.soup(confirm_path)
    response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
    assert response.status_code == 302, "Confirm should redirect forth"

    assert Order.objects.count() == 1
    order = Order.objects.filter(payment_method=payment_method).first()
    assert order.payment_data.get(CIELO_CREDIT_CARD_INFO_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shoop:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
    order_complete_path = reverse("shoop:order_complete",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    assert response.url.endswith(process_payment_path), ("Confirm should have redirected to payment page")

    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Visa,
                                     'produto':CieloProduct.Credit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.Authorized.value,
    )

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
                                                 'nsu':'123'})

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            response = c.get(process_payment_path)
            assert response.status_code == 302, "Payment page should redirect forth"
            assert response.url.endswith(process_payment_return_path)

            order.refresh_from_db()
            assert order.payment_data.get(CIELO_TID_INFO_KEY) == tid

            cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
            assert cielo_transaction.cc_brand == CieloCardBrand.Visa
            assert cielo_transaction.cc_holder == 'Joao de souza'
            assert cielo_transaction.installments == 4
            assert cielo_transaction.cc_product == CieloProduct.InstallmentCredit
            assert abs(cielo_transaction.total.value - order.taxful_total_price_value) < 0.01
            assert cielo_transaction.status.value == transacao.status

            # Check payment return
            response = c.get(process_payment_return_path)
            assert response.status_code == 302, "Payment return should redirect forth"
            assert response.url.endswith(order_complete_path)

            cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
            assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
            assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
            assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

            assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
            assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

            assert cielo_transaction.total_captured.value == Decimal()
            assert cielo_transaction.total_reversed.value == Decimal()

            order.refresh_from_db()
            assert order.payment_status == PaymentStatus.FULLY_PAID
            assert order.payment_data.get(CIELO_CREDIT_CARD_INFO_KEY) is None  # removed key


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

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
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
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})


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
    c.post(payment_path, data={"cc_number": '4012001038443335',
                                          "cc_brand": CieloCardBrand.Visa,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '4'})


    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))
    order = Order.objects.filter(payment_method=payment_method).first()

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})

    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Visa,
                                     'produto':CieloProduct.Credit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.Authorized.value,
    )

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
                                                 'nsu':'123'})

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            # remove de proposito os dados do pagamento
            order.payment_data = {}
            order.save()

            c.get(process_payment_path)

            order.refresh_from_db()
            # pedido cancelado
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

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 10,
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
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})

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
    c.post(payment_path, data={"cc_number": '4012001038443335',
                                          "cc_brand": CieloCardBrand.Visa,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '4'})


    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))
    order = Order.objects.filter(payment_method=payment_method).first()

    # Forja um valor incorreto no total do juros
    order.payment_data[CIELO_INSTALLMENT_INFO_KEY]['interest_total'] = order.payment_data[CIELO_INSTALLMENT_INFO_KEY]['interest_total'] + 1.0
    order.save()

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})

    tid = uuid.uuid4().hex

    transacao = Transacao(
        pedido=dict_to_pedido({'numero':str(order.pk),
                               'valor': decimal_to_int_cents(order.taxful_total_price_value),
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':CieloCardBrand.Visa,
                                     'produto':CieloProduct.Credit,
                                     'parcelas':1}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.Authorized.value,
    )

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
                                                 'nsu':'123'})

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            c.get(process_payment_path)

            order.refresh_from_db()
            # pedido cancelado
            assert order.status == OrderStatus.objects.get_default_canceled()


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

    basket_path = reverse("shoop:basket")
    add_to_basket_resp = c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })
    assert add_to_basket_resp.status_code < 400


    # Create methods
    shipping_method = get_default_shipping_method()
    processor = get_payment_provider(auto_capture=True)
    assert isinstance(processor, CieloWS15PaymentProcessor)

    payment_method = processor.create_service(
        CIELO_SERVICE_DEBIT,
        identifier="cielo_phase_d",
        shop=get_default_shop(),
        name="debit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})


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

    # Phase: Cielo
    response = c.soup(payment_path)
    response = c.post(payment_path, data={"cc_number": '5453010000066167',
                                          "cc_brand": CieloCardBrand.Mastercard,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '1'})

    assert response.status_code == 302, "Valid payment form should redirect forth"
    assert response.url.endswith(confirm_path)

    # Phase: Confirm
    assert Order.objects.count() == 0
    confirm_soup = c.soup(confirm_path)
    response = c.post(confirm_path, data=extract_form_fields(confirm_soup))
    assert response.status_code == 302, "Confirm should redirect forth"

    assert Order.objects.count() == 1
    order = Order.objects.filter(payment_method=payment_method).first()
    assert order.payment_data.get(CIELO_DEBIT_CARD_INFO_KEY)
    assert order.payment_status == PaymentStatus.NOT_PAID

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})
    process_payment_return_path = reverse("shoop:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
    order_complete_path = reverse("shoop:order_complete",kwargs={"pk": order.pk, "key": order.key})

    # Check confirm redirection to payment page
    assert response.url.endswith(process_payment_path), ("Confirm should have redirected to payment page")

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
        # Visit payment page
        response = c.get(process_payment_path)
        assert response.status_code == 302, "Payment page should redirect forth"
        assert response.url.endswith(transacao.url_autenticacao)

        order.refresh_from_db()
        assert order.payment_data.get(CIELO_TID_INFO_KEY) == tid

        cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
        assert cielo_transaction.cc_brand == CieloCardBrand.Mastercard
        assert cielo_transaction.cc_holder == 'Joao de souza'
        assert cielo_transaction.installments == 1
        assert cielo_transaction.cc_product == CieloProduct.Debit
        assert abs(cielo_transaction.total.value - order.taxful_total_price_value) < 0.01
        assert cielo_transaction.status.value == transacao.status

    transacao.status = CieloTransactionStatus.Captured.value
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
    transacao.captura = dict_to_captura({'codigo':'1312',
                                         'mensagem':'capturado',
                                         'data-hora':'2016-01-01T01:00Z',
                                         'valor':decimal_to_int_cents(order.taxful_total_price_value)})

    with patch.object(CieloRequest, 'autorizar', return_value=transacao):
        with patch.object(CieloRequest, 'consultar', return_value=transacao):
            with patch.object(CieloRequest, 'capturar', return_value=transacao):
                # Check payment return
                response = c.get(process_payment_return_path)
                assert response.status_code == 302, "Payment return should redirect forth"
                assert response.url.endswith(order_complete_path)

                cielo_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
                assert cielo_transaction.authorization_nsu == str(transacao.autorizacao.nsu)
                assert cielo_transaction.authorization_lr == str(transacao.autorizacao.lr)
                assert cielo_transaction.authorization_date == iso8601.parse_date(transacao.autorizacao.data_hora)

                assert cielo_transaction.authentication_eci == transacao.autenticacao.eci
                assert cielo_transaction.authentication_date == iso8601.parse_date(transacao.autenticacao.data_hora)

                assert abs(cielo_transaction.total_captured.value - order.taxful_total_price_value) < 0.01
                assert cielo_transaction.total_reversed.value == Decimal()

    order.refresh_from_db()
    assert order.payment_status == PaymentStatus.FULLY_PAID
    assert order.payment_data.get(CIELO_DEBIT_CARD_INFO_KEY) is None  # removed key



@pytest.mark.django_db
def test_save_cc_info():
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    shipping_method = get_default_shipping_method()
    processor = get_payment_provider(auto_capture=True)

    payment_method = processor.create_service(
        CIELO_SERVICE_DEBIT,
        identifier="cielo_phase_d",
        shop=get_default_shop(),
        name="debit card",
        enabled=True,
        tax_class=get_default_tax_class())

    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})

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

    form_cc_info = {
        "cc_number": '5453010000066167',
        "cc_brand": CieloCardBrand.Mastercard,
        "cc_holder": "Joao de souza",
        "cc_valid_year": now().year+1,
        "cc_valid_month": "%02d" % now().month,
        "cc_security_code": "123",
        "installments": '1'
    }
    c.post(payment_path, data=form_cc_info)

    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))

    order = Order.objects.filter(payment_method=payment_method).first()
    cc_info = signing.loads(order.payment_data.get(CIELO_DEBIT_CARD_INFO_KEY))

    assert form_cc_info['cc_number'] == cc_info['cc_number']
    assert form_cc_info['cc_brand'] == cc_info['cc_brand']
    assert form_cc_info['cc_holder'] == cc_info['cc_holder']
    assert str(form_cc_info['cc_valid_year']) == cc_info['cc_valid_year']
    assert str(form_cc_info['cc_valid_month']) == cc_info['cc_valid_month']
    assert form_cc_info['cc_security_code'] == cc_info['cc_security_code']
    assert str(form_cc_info['installments']) == cc_info['installments']


@pytest.mark.django_db
def test_change_cart_half_way():
    """
        Caso:
            - Sem autenticacao
            - Sem auto-captura
            - Parcelado 3x
            - Usuário altera carrinho depois de selecionar parcelas
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    shipping_method = get_default_shipping_method()
    processor = get_payment_provider(installments_without_interest=1)

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})

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

    form_cc_info = {
        "cc_number": '5453010000066167',
        "cc_brand": CieloCardBrand.Mastercard,
        "cc_holder": "Joao de souza",
        "cc_valid_year": now().year+1,
        "cc_valid_month": "%02d" % now().month,
        "cc_security_code": "123",
        "installments": '3'
    }
    c.post(payment_path, data=form_cc_info)

    response = c.get(confirm_path)
    assert response.status_code == 200
    confirm_soup = c.soup(confirm_path)

    # adiciona mais um produto no carrinho
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    # tenta fechar o pedido com os dados antigos
    response = c.post(confirm_path, data=extract_form_fields(confirm_soup))

    # deve redirecionar o usuário para a pagina de pagamento
    assert response.status_code == 302
    assert response.url.endswith(payment_path)

    # salva os dados do cartao de novo
    c.post(payment_path, data=form_cc_info)
    confirm_soup = c.soup(confirm_path)

    # agora vai!
    response = c.post(confirm_path, data=extract_form_fields(confirm_soup))

    order = Order.objects.filter(payment_method=payment_method).first()
    cc_info = signing.loads(order.payment_data.get(CIELO_CREDIT_CARD_INFO_KEY))

    assert form_cc_info['cc_number'] == cc_info['cc_number']
    assert form_cc_info['cc_brand'] == cc_info['cc_brand']
    assert form_cc_info['cc_holder'] == cc_info['cc_holder']
    assert str(form_cc_info['cc_valid_year']) == cc_info['cc_valid_year']
    assert str(form_cc_info['cc_valid_month']) == cc_info['cc_valid_month']
    assert form_cc_info['cc_security_code'] == cc_info['cc_security_code']
    assert str(form_cc_info['installments']) == cc_info['installments']


@pytest.mark.django_db
def test_installment_interest():
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 3,
        "supplier": get_default_supplier().pk
    })

    shipping_method = get_default_shipping_method()
    processor = get_payment_provider(installments_without_interest=1)

    payment_method = processor.create_service(
        CIELO_SERVICE_CREDIT,
        identifier="cielo_phase_cc",
        shop=get_default_shop(),
        name="credit card",
        enabled=True,
        tax_class=get_default_tax_class())

    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})

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

    form_cc_info = {
        "cc_number": '5453010000066167',
        "cc_brand": CieloCardBrand.Mastercard,
        "cc_holder": "Joao de souza",
        "cc_valid_year": now().year+1,
        "cc_valid_month": "%02d" % now().month,
        "cc_security_code": "123",
        "installments": '3'
    }
    c.post(payment_path, data=form_cc_info)

    response = c.get(confirm_path)
    assert response.status_code == 200
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))
    order = Order.objects.filter(payment_method=payment_method).first()

    # calcula o juros que havera no pedido com o parcelamento
    payment_method_total = sum([line.price.value for line in order.lines.filter(type=OrderLineType.PAYMENT)])
    product_total = sum([line.price.value for line in order.lines.filter(type=OrderLineType.PRODUCT)])
    assert payment_method_total > 0
    assert order.taxful_total_price_value == (payment_method_total + product_total)


@pytest.mark.django_db
def test_error_response_tid_doesnt_exist():
    """
        Caso:
            - Transação com Cartão de Débito
            - Auto captura DESABILITADO
            - Com URL para autenticação
            - 1 parcela
            - ERRO: Transação não existe em process_payment_return_request
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shoop:basket")
    c.post(basket_path, data={
        "command": "add",
        "product_id": default_product.pk,
        "quantity": 1,
        "supplier": get_default_supplier().pk
    })

    shipping_method = get_default_shipping_method()
    processor = get_payment_provider(auto_capture=True)

    payment_method = processor.create_service(
        CIELO_SERVICE_DEBIT,
        identifier="cielo_phase_d",
        shop=get_default_shop(),
        name="debit card",
        enabled=True,
        tax_class=get_default_tax_class())

    # Resolve paths
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})

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

    process_payment_return_path = reverse("shoop:order_process_payment_return",kwargs={"pk": order.pk, "key": order.key})
    c.post(process_payment_return_path)
    # Order must be cancelled
    order.refresh_from_db()
    assert order.status == OrderStatus.objects.get_default_canceled()


@pytest.mark.django_db
def test_credit_card_non_authorized_error():
    """
        Caso:
            - Transação com Cartão de Crédito
            - Auto captura desabilidato
            - Sem URL para autenticação
            - 1 parcela sem juros
            - Transação negada
    """
    initialize()

    c = SmartClient()
    default_product = get_default_product()

    basket_path = reverse("shoop:basket")
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
    addresses_path = reverse("shoop:checkout", kwargs={"phase": "addresses"})
    methods_path = reverse("shoop:checkout", kwargs={"phase": "methods"})
    payment_path = reverse("shoop:checkout", kwargs={"phase": "payment"})
    confirm_path = reverse("shoop:checkout", kwargs={"phase": "confirm"})


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
    c.post(payment_path, data={"cc_number": '4012001038443335',
                                          "cc_brand": CieloCardBrand.Visa,
                                          "cc_holder": "Joao de souza",
                                          "cc_valid_year": now().year+1,
                                          "cc_valid_month": "%02d" % now().month,
                                          "cc_security_code": "123",
                                          "installments": '1'})

    # Phase: Confirm
    confirm_soup = c.soup(confirm_path)
    c.post(confirm_path, data=extract_form_fields(confirm_soup))
    order = Order.objects.filter(payment_method=payment_method).first()

    process_payment_path = reverse("shoop:order_process_payment", kwargs={"pk": order.pk, "key": order.key})

    # Testa erro de código seguranca invalido
    with patch.object(CieloRequest, 'autorizar') as mocked:
        mocked.side_effect = CieloRequestError('8 - {0}'.format(CieloErrorMap[8]))
        response = c.get(process_payment_path)
        assert str(response.content).index("Unknown error") >= 0

    with patch.object(CieloRequest, 'autorizar') as mocked:
        mocked.side_effect = CieloRequestError('17 - {0}'.format(CieloErrorMap[17]))
        response = c.get(process_payment_path)
        assert str(response.content).index("Invalid security code") >= 0
