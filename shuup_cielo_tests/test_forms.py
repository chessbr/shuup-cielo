# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from django.utils.timezone import now
import pytest

from shuup_cielo.constants import (
    CIELO_SERVICE_CREDIT, CIELO_SERVICE_DEBIT, CieloAuthorizationType, CieloCardBrand, InterestType
)
from shuup_cielo.forms import CieloPaymentForm
from shuup_cielo.models import CieloConfig


def get_cielo_config():
    cielo_config = CieloConfig.objects.create()
    cielo_config.ec_num=''
    cielo_config.ec_key=''
    cielo_config.auto_capture=False
    cielo_config.authorization_mode=CieloAuthorizationType.IfAuthenticatedOrNot
    cielo_config.max_installments=4
    cielo_config.installments_without_interest=3
    cielo_config.interest_type=InterestType.Simple
    cielo_config.interest_rate=2
    cielo_config.min_installment_amount=5
    cielo_config.sandbox=True
    cielo_config.save()
    return cielo_config


@pytest.mark.django_db
def test_form_validate():
    # invalid CC and expiration date
    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'39039120321',
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
    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'4012001038443335',
                                           'cc_brand':CieloCardBrand.Visa,
                                           'cc_holder':'portador',
                                           'cc_security_code':'122',
                                           'cc_valid_year': now().year + 1,
                                           'cc_valid_month': "%2d" % int(now().month),
                                           'installments': 2})
    assert form.is_valid() == True
    assert len(form.non_field_errors()) == 0


    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'4012001038443335',
                                                        'cc_brand':CieloCardBrand.Visa,
                                                        'cc_holder':'portador',
                                                        'cc_security_code':'122',
                                                        'cc_valid_year': now().year + 1,
                                                        'cc_valid_month': "%2d" % int(now().month),
                                                        'installments': 2})
    assert form.is_valid() == True
    assert len(form.non_field_errors()) == 0


    # bandeira nao aceita parcelado
    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'6011020000245045',
                                                        'cc_brand':CieloCardBrand.Discover,
                                                        'cc_holder':'portador',
                                                        'cc_security_code':'122',
                                                        'cc_valid_year': now().year + 1,
                                                        'cc_valid_month': "%2d" % int(now().month),
                                                        'installments': 2})
    assert form.is_valid() == False
    assert len(form.non_field_errors()) == 0

    # discover ok
    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'6011020000245045',
                                                        'cc_brand':CieloCardBrand.Discover,
                                                        'cc_holder':'portador',
                                                        'cc_security_code':'122',
                                                        'cc_valid_year': now().year + 1,
                                                        'cc_valid_month': "%2d" % int(now().month),
                                                        'installments': 1})
    assert form.is_valid() == True
    assert len(form.non_field_errors()) == 0


    # amex aceita só 4 digitos no codigo verificador
    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'4012001038443335',
                                                       'cc_brand':CieloCardBrand.Amex,
                                                       'cc_holder':'portador',
                                                       'cc_security_code':'122',
                                                       'cc_valid_year': now().year + 1,
                                                       'cc_valid_month': "%2d" % int(now().month),
                                                       'installments': 2})
    assert form.is_valid() == False
    assert len(form.non_field_errors()) == 0
    assert 'cc_security_code' in form.errors  # invalid security code



    form = CieloPaymentForm(CIELO_SERVICE_CREDIT, data={'cc_number':'4012001038443335',
                                                        'cc_brand':CieloCardBrand.Visa,
                                                        'cc_holder':'portador',
                                                        'cc_security_code':'122',
                                                        'cc_valid_year': "",
                                                        'cc_valid_month': "",
                                                        'installments': 2})
    assert form.is_valid() == False
    assert 'cc_valid_year' in form.errors  # invalid exp data
