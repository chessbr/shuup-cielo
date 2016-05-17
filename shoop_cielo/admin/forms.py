# -*- coding: utf-8 -*-
# This file is part of Shoop Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import unicode_literals

from shoop_cielo.models import CieloWS15PaymentProcessor

from django import forms

from shoop.admin.forms import ShoopAdminForm


class CieloWS15PaymentProcessorForm(ShoopAdminForm):
    class Meta:
        model = CieloWS15PaymentProcessor
        exclude = ["identifier"]
        widgets = {
            'ec_key': forms.PasswordInput(render_value=True),
        }
