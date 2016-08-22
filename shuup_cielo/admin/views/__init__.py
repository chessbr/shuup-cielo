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

from django.http.response import HttpResponseBadRequest, HttpResponseServerError
from django.shortcuts import render_to_response
from django.views.generic.base import TemplateView, View

from cielo_webservice.exceptions import CieloRequestError
import shuup_cielo
from shuup_cielo.constants import CieloTransactionStatus
from shuup_cielo.models import CieloTransaction

TRANSACTION_DETAIL_TEMPLAE = 'cielo/admin/order_section_transaction_detail.jinja'


class DashboardView(TemplateView):
    template_name = "cielo/admin/dashboard.jinja"
    title = "Cielo"

    def get_context_data(self, **kwargs):
        context_data = super(DashboardView, self).get_context_data(**kwargs)
        context_data.update({'VERSION': shuup_cielo.__version__})
        return context_data


class RefreshTransactionView(View):
    '''
    Atualiza uma transação e retorna o detalhe da transação renderizado
    '''

    def post(self, request, *args, **kwargs):
        try:
            cielo_transaction = CieloTransaction.objects.get(pk=request.POST.get('id'))
            cielo_transaction.refresh()
            return render_to_response(TRANSACTION_DETAIL_TEMPLAE, {'transaction': cielo_transaction,
                                                                   'CieloTransactionStatus': CieloTransactionStatus})

        except Exception as exc:
            return HttpResponseServerError(str(exc))


class CaptureTransactionView(View):
    '''
    Captura uma transação (total ou parcialmente) e retorna o detalhe da transação renderizado
    '''

    def post(self, request, *args, **kwargs):
        '''
        :param: id: ID da transação
        :param: amount: Valor a ser cancelado ou Nulo se for total
        :type: id: int
        :type: amount: decimal.Decimal|None
        '''

        try:
            cielo_transaction = CieloTransaction.objects.get(pk=request.POST.get('id'))
            amount = Decimal(request.POST.get('amount', cielo_transaction.total_value))

            try:
                cielo_transaction.capture(amount)
            except CieloRequestError as err:
                return HttpResponseBadRequest("{0}".format(err))

            return render_to_response(TRANSACTION_DETAIL_TEMPLAE, {'transaction': cielo_transaction,
                                                                   'CieloTransactionStatus': CieloTransactionStatus})

        except Exception as exc:
            return HttpResponseServerError("{0}".format(exc))


class CancelTransactionView(View):
    '''
    Cancela uma transação (total ou parcialmente) e retorna o detalhe da transação renderizado
    '''

    def post(self, request, *args, **kwargs):
        '''
        :param: id: ID da transação
        :param: amount: Valor a ser cancelado ou Nulo se for total
        :type: id: int
        :type: amount: decimal.Decimal|None
        '''

        try:
            cielo_transaction = CieloTransaction.objects.get(pk=request.POST.get('id'))
            amount = Decimal(request.POST.get('amount', cielo_transaction.total_value))

            try:
                cielo_transaction.cancel(amount)
            except CieloRequestError as err:
                return HttpResponseBadRequest("{0}".format(err))

            return render_to_response(TRANSACTION_DETAIL_TEMPLAE, {'transaction': cielo_transaction,
                                                                   'CieloTransactionStatus': CieloTransactionStatus})

        except Exception as exc:
            return HttpResponseServerError("{0}".format(exc))
