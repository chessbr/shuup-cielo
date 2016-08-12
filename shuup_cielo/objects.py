# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

CIELO_TRANSACTION_ID_KEY = 'cielo_transaction_id'
CIELO_ORDER_TRANSACTION_ID_KEY = 'cielo_order_transaction_id'


class CieloTransactionContext(object):
    _request = None
    _transaction = None
    _order_transaction = None

    def commit(self):
        """ Persists the current session objects """
        self._request.session.modified = True

        if self._transaction:
            self._request.session[CIELO_TRANSACTION_ID_KEY] = self._transaction.pk
        else:
            self._request.session[CIELO_TRANSACTION_ID_KEY] = None

        if self._order_transaction:
            self._request.session[CIELO_ORDER_TRANSACTION_ID_KEY] = self._order_transaction.pk
        else:
            self._request.session[CIELO_ORDER_TRANSACTION_ID_KEY] = None

    def rollback(self):
        """ Cancel the current transaction if it exists """
        if self._transaction:
            self._transaction.safe_cancel(self._transaction.total_value)

    def clear(self):
        """ Set the current attributs to None and commit """
        self._transaction = None
        self._order_transaction = None
        self.commit()

    def set_request(self, request):
        self._request = request

    def set_transaction(self, transaction):
        self._transaction = transaction

    def set_order_transaction(self, order_transaction):
        self._order_transaction = order_transaction

    @property
    def transaction(self):
        return self._transaction

    @property
    def order_transaction(self):
        return self._order_transaction
