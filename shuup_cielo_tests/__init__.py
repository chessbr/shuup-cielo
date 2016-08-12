# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

from decimal import Decimal

from shuup_cielo.constants import CieloCardBrand, CieloProduct, CieloTransactionStatus
from shuup_cielo.utils import decimal_to_int_cents

from django.utils.timezone import now

from cielo_webservice.models import (
    dict_to_autenticacao, dict_to_autorizacao, dict_to_cancelamento, dict_to_captura,
    dict_to_pagamento, dict_to_pedido, Transacao
)

PRODUCT_PRICE = Decimal(15.0)


AUTH_URL = 'http://CUSTUM_URL'


CC_VISA_1X_INFO = {
    "cc_number":'4012001038443335',
    "cc_brand": CieloCardBrand.Visa,
    "cc_holder": "Joao de souza",
    "cc_valid_year": now().year+1,
    "cc_valid_month": "%02d" % now().month,
    "cc_security_code": "123",
    "installments":1
}


CC_VISA_4X_INFO = {
    "cc_number":'4012001038443335',
    "cc_brand": CieloCardBrand.Visa,
    "cc_holder": "Joao de souza",
    "cc_valid_year": now().year+1,
    "cc_valid_month": "%02d" % now().month,
    "cc_security_code": "123",
    "installments":4
}

CC_MASTER_1X_INFO = {
    "cc_number": '5453010000066167',
    "cc_brand": CieloCardBrand.Mastercard,
    "cc_holder": "Joao de souza",
    "cc_valid_year": now().year+1,
    "cc_valid_month": "%02d" % now().month,
    "cc_security_code": "123",
    "installments":1
}


def get_in_progress_transaction(numero=1, valor="", produto="", bandeira="", parcelas=1, tid="", return_url=AUTH_URL):
    return Transacao(
        pedido=dict_to_pedido({'numero':str(numero),
                               'valor':valor,
                               'moeda':941,
                               'data-hora':'2016-01-01T01:00Z'}),
        pagamento=dict_to_pagamento({'bandeira':bandeira, # CieloCardBrand.Visa,
                                     'produto':produto, # CieloProduct.Credit,
                                     'parcelas':parcelas}),
        token=None,
        captura=None,
        cancelamento=None,
        tid=tid,
        pan=None,
        status=CieloTransactionStatus.InProgress.value,
        url_autenticacao=return_url,
    )


def get_approved_transaction(pending_transaction):
    pending_transaction.status = CieloTransactionStatus.Authorized.value
    pending_transaction.autenticacao = dict_to_autenticacao({'codigo':'13123',
                                                 'mensagem':'autorizado',
                                                 'data-hora':'2016-01-01T01:00Z',
                                                 'valor':pending_transaction.pedido.valor,
                                                 'eci':2})
    pending_transaction.autorizacao = dict_to_autorizacao({'codigo':'31321',
                                               'mensagem':'autenticar',
                                               'data-hora':'2016-01-01T01:00Z',
                                               'valor':pending_transaction.pedido.valor,
                                               'lr':"00",
                                               'nsu':'123'})
    return pending_transaction


def get_captured_transaction(approved_transaction):
    approved_transaction.status = CieloTransactionStatus.Captured.value
    approved_transaction.captura = dict_to_captura({
        'codigo':'1312',
        'mensagem':'capturado',
        'data-hora':'2016-01-01T01:00Z',
        'valor':approved_transaction.pedido.valor
    })
    return approved_transaction


def get_cancelled_transaction(transacao):
    transacao.status = CieloTransactionStatus.Cancelled.value
    transacao.cancelamento = dict_to_cancelamento({
        'cancelamento': {
            'codigo':'1312',
            'mensagem':'cancelado',
            'data-hora':'2016-01-01T01:00Z',
            'valor':transacao.pedido.valor
        }
    })
    return transacao
