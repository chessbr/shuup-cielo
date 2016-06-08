# -*- coding: utf-8 -*-
# This file is part of Shoop Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from django.utils.translation import ugettext_lazy as _

from shoop.admin.base import AdminModule, MenuEntry
from shoop.admin.currencybound import CurrencyBound
from shoop.admin.utils.urls import admin_url


class CieloModule(CurrencyBound, AdminModule):
    name = _("Cielo")
    breadcrumbs_menu_entry = MenuEntry(name, url="shoop_admin:cielo.dashboard")

    def get_urls(self):
        return [
            admin_url(
                "^cielo/transaction/refresh/$",
                "shoop_cielo.admin.views.RefreshTransactionView",
                name="cielo.transaction-refresh"
            ),
            admin_url(
                "^cielo/transaction/capture/$",
                "shoop_cielo.admin.views.CaptureTransactionView",
                name="cielo.transaction-capture"
            ),
            admin_url(
                "^cielo/transaction/cancel/$",
                "shoop_cielo.admin.views.CancelTransactionView",
                name="cielo.transaction-cancel"
            ),
            admin_url(
                "^cielo/$",
                "shoop_cielo.admin.views.DashboardView",
                name="cielo.dashboard"
            ),
        ]

    def get_menu_entries(self, request):
        category = _("Cielo")
        return [
            MenuEntry(
                text="Cielo",
                icon="fa fa-credit-card",
                url="shoop_admin:cielo.dashboard",
                category=category,
                aliases=[_("Show Dashboard")]
            ),
        ]
