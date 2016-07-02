# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from decimal import Decimal

import pytest

from shuup_cielo.constants import CieloAuthorizationType, CieloCardBrand, InterestType
from shuup_cielo.forms import CieloPaymentForm
from shuup_cielo.models import CieloWS15PaymentProcessor, InstallmentContext

from django import forms
from django.conf import settings
from django.utils.timezone import now

from shuup.testing.factories import (
    _get_service_provider, DEFAULT_IDENTIFIER, get_default_shop, get_default_tax_class
)


def get_payment_method():
    identifier = DEFAULT_IDENTIFIER
    service = CieloWS15PaymentProcessor.objects.filter(identifier=identifier).first()

    if not service:
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
        provider.save()

        service = provider.create_service(
            None, identifier=identifier,
            shop=get_default_shop(),
            enabled=True,
            name="CieloWS15PaymentProcessor",
            tax_class=get_default_tax_class()
        )
    assert service.pk and service.identifier == identifier
    assert service.shop == get_default_shop()
    return service


@pytest.mark.django_db
def test_form_installment_context():
    form = CieloPaymentForm()
    assert form.installment_context is None
    assert form.currency == settings.SHUUP_HOME_CURRENCY
    assert len(form.fields['installments'].choices) == 1
    assert isinstance(form.fields['installments'].widget, forms.HiddenInput)

    payment_method = get_payment_method()
    context = InstallmentContext(Decimal(300), payment_method.payment_processor)
    form = CieloPaymentForm(context)
    assert form.installment_context is context
    assert form.currency == settings.SHUUP_HOME_CURRENCY

    assert context.installment_total_amount == Decimal(300)
    assert context.max_installments == payment_method.payment_processor.max_installments
    assert context.installments_without_interest == payment_method.payment_processor.installments_without_interest
    assert context.interest_type == payment_method.payment_processor.interest_type
    assert context.interest_rate == payment_method.payment_processor.interest_rate
    assert context.min_installment_amount == payment_method.payment_processor.min_installment_amount

    # possui parcelas
    assert len(form.fields['installments'].choices) == len(context.get_intallments_choices())
    assert isinstance(form.fields['installments'].widget, forms.Select)

    # context que valor é pequeno e nao tem parcelamento
    context = InstallmentContext(Decimal(1), payment_method.payment_processor)
    form = CieloPaymentForm(context)
    assert len(form.fields['installments'].choices) == 1
    assert isinstance(form.fields['installments'].widget, forms.HiddenInput)


@pytest.mark.django_db
def test_form_validate():
    payment_method = get_payment_method()
    context = InstallmentContext(Decimal(300), payment_method.payment_processor)


    # invalid CC and expiration date
    form = CieloPaymentForm(context, data={'cc_number':'39039120321',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year':'2015',
                                           'cc_valid_month': '02',
                                           'installments': 2})
    assert form.is_valid() == False
    assert 'cc_number' in form.errors   # cc invalida
    assert 'cc_valid_year' in form.errors  # invalid exp data
    assert len(form.non_field_errors()) == 0

    # all ok
    form = CieloPaymentForm(context, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': now().year + 1,
                                           'cc_valid_month': "%2d" % int(now().month),
                                           'installments': 2})
    assert form.is_valid() == True
    assert len(form.non_field_errors()) == 0



    # muda forma de calculo de juros - tudo ok
    context.interest_type = InterestType.Price
    form = CieloPaymentForm(context, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': now().year + 1,
                                           'cc_valid_month': "%2d" % int(now().month),
                                           'installments': 2})
    assert form.is_valid() == True
    assert len(form.non_field_errors()) == 0


    # bandeira nao aceita parcelado
    form = CieloPaymentForm(context, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Discover,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': now().year + 1,
                                           'cc_valid_month': "%2d" % int(now().month),
                                           'installments': 2})
    assert form.is_valid() == True
    assert int(form.cleaned_data['installments']) == 1
    assert len(form.non_field_errors()) == 0


    # muda o total a ser parcelado e atribui a quantidade de parcelas escolhidas errada
    context.installment_total_amount = Decimal(2)
    form = CieloPaymentForm(context, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': now().year + 1,
                                           'cc_valid_month': "%2d" % int(now().month),
                                           'installments': 2})
    assert form.is_valid() == False
    assert len(form.non_field_errors()) == 0
    assert 'installments' in form.errors  # wrong installmnet



    form = CieloPaymentForm(context, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': "",
                                           'cc_valid_month': "",
                                           'installments': 2})
    assert form.is_valid() == False
    assert 'cc_valid_year' in form.errors  # invalid exp data
