# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.


from shuup.apps import AppConfig


class ShuupCieloAppConfig(AppConfig):
    name = "shuup_cielo"
    verbose_name = "Shuup Cielo"
    provides = {
        "service_provider_admin_form": [
            "shuup_cielo.admin.forms:CieloPaymentProcessorForm"
        ],
        "service_behavior_component_form": [
            "shuup_cielo.admin.forms:DiscountPercentageBehaviorComponentForm"
        ],
        "front_service_checkout_phase_provider": [
            "shuup_cielo.checkout:CieloCheckoutPhaseProvider"
        ],
        "front_urls_pre": [
            "shuup_cielo.urls:urlpatterns"
        ],
        "admin_order_section": [
             "shuup_cielo.admin.order_section:CieloOrderSection"
        ],
        "admin_module": [
            "shuup_cielo.admin:CieloModule",
            "shuup_cielo.admin:CieloConfigModule"
        ]
    }
