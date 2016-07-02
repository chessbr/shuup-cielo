# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from shuup_cielo.constants import CieloTransactionStatus
from shuup_cielo.models import CieloWS15PaymentProcessor, CieloWS15Transaction

from shuup.admin.base import OrderSection


class CieloOrderSection(OrderSection):
    identifier = 'cielows15'
    name = 'Cielo'
    icon = 'fa-credit-card'
    template = 'cielo/admin/order_section.jinja'
    extra_js = 'cielo/admin/order_section_extra_js.jinja'
    order = 10

    @staticmethod
    def visible_for_order(order):
        return isinstance(order.payment_method.payment_processor, CieloWS15PaymentProcessor)

    @staticmethod
    def get_context_data(order):
        return {
            'CieloTransactionStatus': CieloTransactionStatus,
            'transactions': CieloWS15Transaction.objects.filter(order=order).order_by('id')
        }
