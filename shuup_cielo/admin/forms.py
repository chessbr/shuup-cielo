# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import unicode_literals

from shuup_cielo.models import CieloWS15PaymentProcessor,\
    DiscountPercentageBehaviorComponent

from shuup.admin.forms import ShuupAdminForm

from django import forms


class CieloWS15PaymentProcessorForm(ShuupAdminForm):
    class Meta:
        model = CieloWS15PaymentProcessor
        exclude = ["identifier"]
        widgets = {
            'ec_key': forms.PasswordInput(render_value=True),
        }


class DiscountPercentageBehaviorComponentForm(forms.ModelForm):
    class Meta:
        model = DiscountPercentageBehaviorComponent
        exclude = ["identifier"]
