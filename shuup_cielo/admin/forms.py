# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import unicode_literals

from django import forms

from shuup.admin.forms import ShuupAdminForm
from shuup_cielo.models import (
    CieloConfig, CieloPaymentProcessor, DiscountPercentageBehaviorComponent
)


class CieloPaymentProcessorForm(ShuupAdminForm):
    class Meta:
        model = CieloPaymentProcessor
        exclude = ["identifier"]
        widgets = {
            'ec_key': forms.PasswordInput(render_value=True),
        }


class DiscountPercentageBehaviorComponentForm(forms.ModelForm):
    class Meta:
        model = DiscountPercentageBehaviorComponent
        exclude = ["identifier"]


class CieloConfigForm(forms.ModelForm):
    class Meta:
        model = CieloConfig
        exclude = []
