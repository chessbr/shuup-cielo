# -*- coding: utf-8 -*-
# This file is part of Shoop Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

import calendar
from datetime import datetime

from shoop_cielo.constants import (
    CIELO_CARD_BRAND_CHOICES, CieloProduct, CieloProductMatrix,
    INSTALLMENT_CHOICE_WITH_INTEREST_STRING, INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING
)
from shoop_cielo.utils import is_cc_valid, safe_int

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from shoop.utils.i18n import format_money
from shoop.utils.money import Money


class CieloPaymentForm(forms.Form):
    cc_brand = forms.ChoiceField(label=_('Brand'), required=True,
                                 choices=CIELO_CARD_BRAND_CHOICES)
    cc_holder = forms.CharField(label=_('Holder'), required=True, max_length=50)
    cc_number = forms.CharField(label=_('Number'), required=True, max_length=20)
    cc_security_code = forms.CharField(label=_('Security code'), required=True,
                                       max_length=4, min_length=3)
    cc_valid_year = forms.CharField(label=_('Valid year'), required=True,
                                    max_length=4, min_length=4)
    cc_valid_month = forms.CharField(label=_('Valid month'), required=True,
                                     max_length=2, min_length=2)
    installments = forms.ChoiceField(label=_('Number of installments'),
                                     required=True,
                                     initial=1,
                                     choices=[(1, '1x')])  # Only 1 installment is enabled by default

    def __init__(self, installment_context=None, currency=settings.SHOOP_HOME_CURRENCY, *args, **kwargs):
        self.installment_context = installment_context
        self.currency = currency
        super(CieloPaymentForm, self).__init__(*args, **kwargs)

        # com o contexto de parcelamento, cria e popula o choicefield
        if installment_context:
            installment_choices = []

            choices = installment_context.get_intallments_choices()

            for installment, installment_amount, installments_total, interest_total in choices:

                if interest_total > 0.01:
                    label = INSTALLMENT_CHOICE_WITH_INTEREST_STRING.format(installment,
                                                                           format_money(Money(installment_amount, currency)),
                                                                           format_money(Money(installments_total, currency)),
                                                                           installment_context.interest_rate)
                else:
                    label = INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING.format(installment,
                                                                              format_money(Money(installment_amount, currency)),
                                                                              format_money(Money(installments_total, currency)),
                                                                              installment_context.interest_rate)

                installment_choices.append(
                    (installment, label)
                )

            # vamos garantir que ao menos uma parcela tenha sido calculada antes de substituir o valor default
            if installment_choices:
                self.fields['installments'].choices = installment_choices
            else:
                # sem parcelamento, não precisa apresentar o widget
                self.fields['installments'].widget = forms.HiddenInput()
        else:
            # sem parcelamento, não precisa apresentar o widget
            self.fields['installments'].widget = forms.HiddenInput()

    def clean_cc_number(self):
        cc_number = self.cleaned_data.get('cc_number')

        if not is_cc_valid(cc_number):
            raise ValidationError(_('Invalid card number'))

        return cc_number

    def clean(self):
        cleaned = super(CieloPaymentForm, self).clean()

        # Bandeira não aceita parcelado, força apenas 1 parcela
        if not CieloProductMatrix.get(cleaned.get('cc_brand'), {}).get(CieloProduct.InstallmentCredit):
            cleaned['installments'] = 1

        try:
            cc_valid_year = safe_int(cleaned.get('cc_valid_year'))
            cc_valid_month = safe_int(cleaned.get('cc_valid_month'))
            cc_valid_day = calendar.monthrange(cc_valid_year, cc_valid_month)[1]
            cc_valid_until = datetime(year=cc_valid_year, month=cc_valid_month, day=cc_valid_day)

            if timezone.now().date() >= cc_valid_until.date():
                self.add_error('cc_valid_year', _('Your card is expired'))

        except ValueError:
            self.add_error('cc_valid_year', _('Invalid expiration date'))

        return cleaned
