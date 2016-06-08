# -*- coding: utf-8 -*-
# This file is part of Shoop Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.


from shoop.apps import AppConfig


class ShoopCieloAppConfig(AppConfig):
    name = "shoop_cielo"
    verbose_name = "Shoop Cielo"
    provides = {
        "service_provider_admin_form": [
            "shoop_cielo.admin.forms:CieloWS15PaymentProcessorForm",
        ],
        "front_service_checkout_phase_provider": [
            "shoop_cielo.checkout:CieloCheckoutPhaseProvider"
        ],
        "admin_order_section": [
             "shoop_cielo.admin.order_section:CieloOrderSection"
        ],
        "admin_module": [
            "shoop_cielo.admin:CieloModule",
        ]
    }
