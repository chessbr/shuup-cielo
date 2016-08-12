# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

from shuup_cielo.models import CieloOrderTransaction, CieloTransaction
from shuup_cielo.objects import (
    CIELO_ORDER_TRANSACTION_ID_KEY, CIELO_TRANSACTION_ID_KEY, CieloTransactionContext
)


class CieloTransactionMiddleware(object):
    """
    Fetches the current session's CieloTransactionContext object
    or create a brand new and set it as a request attribute called `cielo`.
    """

    def process_request(self, request):
        cielo_context = CieloTransactionContext()

        if request.session.get(CIELO_TRANSACTION_ID_KEY):
            cielo_context.set_transaction(
                CieloTransaction.objects.filter(pk=request.session[CIELO_TRANSACTION_ID_KEY]).first()
            )

        if request.session.get(CIELO_ORDER_TRANSACTION_ID_KEY):
            cielo_context.set_order_transaction(
                CieloOrderTransaction.objects.filter(
                    pk=request.session[CIELO_ORDER_TRANSACTION_ID_KEY]
                ).first()
            )

        # coloca o atributo
        request.cielo = cielo_context
        request.cielo.set_request(request)

    def process_response(self, request, response):
        request.cielo.commit()
        return response
