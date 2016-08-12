# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from shuup_cielo.constants import CieloTransactionStatus
from shuup_cielo.models import CieloPaymentProcessor, CieloTransaction

from shuup.admin.base import OrderSection


class CieloOrderSection(OrderSection):
    identifier = 'cielo'
    name = 'Cielo'
    icon = 'fa-credit-card'
    template = 'cielo/admin/order_section.jinja'
    extra_js = 'cielo/admin/order_section_extra_js.jinja'
    order = 10

    @staticmethod
    def visible_for_order(order):
        return isinstance(order.payment_method.payment_processor, CieloPaymentProcessor)

    @staticmethod
    def get_context_data(order):
        return {
            'CieloTransactionStatus': CieloTransactionStatus,
            'transactions': CieloTransaction.objects.filter(order_transaction__order=order).order_by('id')
        }
