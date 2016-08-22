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
import logging

from django.contrib import messages
from django.utils.translation import ugettext as _p
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import TemplateView

from shuup.front.checkout import BasicServiceCheckoutPhaseProvider, CheckoutPhaseViewMixin
from shuup_cielo.constants import (
    CIELO_AUTHORIZED_STATUSES, CIELO_DECIMAL_PRECISION, CIELO_SERVICE_CREDIT, CIELO_SERVICE_DEBIT,
    CIELO_UKNOWN_ERROR_MSG, CieloAuthorizationCode, CieloProduct
)
from shuup_cielo.forms import CieloPaymentForm
from shuup_cielo.models import CieloPaymentProcessor
from shuup_cielo.objects import CIELO_ORDER_TRANSACTION_ID_KEY, CIELO_TRANSACTION_ID_KEY

logger = logging.getLogger(__name__)


class CieloCheckoutPhase(CheckoutPhaseViewMixin, TemplateView):
    template_name = 'cielo/checkout.jinja'
    identifier = 'cielo'
    _title_pending = _('Payment information')
    _title_paid = _('Edit payment information')

    @property
    def title(self):
        if self._has_valid_transaction():
            return self._title_paid
        else:
            return self._title_pending

    def get_context_data(self, **kwargs):
        context = super(CieloCheckoutPhase, self).get_context_data(**kwargs)
        form_kwargs = {}

        if self.request.basket.payment_method_id:
            form_kwargs['service'] = self.request.basket.payment_method.choice_identifier

        context['has_valid_transaction'] = self._has_valid_transaction()
        context['next_phase'] = self.next_phase
        context['form'] = CieloPaymentForm(**form_kwargs)
        return context

    def is_valid(self):
        if self._has_valid_transaction():
            cielo_transaction = self.request.cielo.transaction

            if cielo_transaction.refresh() and \
                    cielo_transaction.authorization_lr in CIELO_AUTHORIZED_STATUSES:
                return True

            else:
                error = _p("Transaction not authorized: {0}").format(
                    CieloAuthorizationCode.get(
                        cielo_transaction.authorization_lr, {}
                    ).get('msg', CIELO_UKNOWN_ERROR_MSG)
                )
                messages.error(self.request, error)

        self.request.cielo.rollback()
        self.request.cielo.clear()

        return False

    def _has_valid_transaction(self):
        """
        This must return True if a valid transaction is in the user session
        """
        cielo_order = self.request.cielo.order_transaction
        cielo_transaction = self.request.cielo.transaction

        # the instances should be valid
        if cielo_order and cielo_transaction:
            service = self.request.basket.payment_method.choice_identifier
            is_credit = (cielo_transaction.cc_product in (CieloProduct.Credit, CieloProduct.InstallmentCredit))
            is_debit = (cielo_transaction.cc_product == CieloProduct.Debit)

            # the service must match the cc product
            if (service == CIELO_SERVICE_CREDIT and is_credit) or (service == CIELO_SERVICE_DEBIT and is_debit):
                order_total = self.request.basket.taxful_total_price.value

                # All clear: valor da transação igual ao total do carrinho!
                if abs((cielo_transaction.total_value - order_total).quantize(CIELO_DECIMAL_PRECISION)) <= Decimal(0):
                    return True

        return False

    def process(self):
        cielo_order = self.request.cielo.order_transaction
        cielo_transaction = self.request.cielo.transaction

        self.request.basket.payment_data[CIELO_TRANSACTION_ID_KEY] = cielo_transaction.pk
        self.request.basket.payment_data[CIELO_ORDER_TRANSACTION_ID_KEY] = cielo_order.pk
        self.request.basket.save()


class CieloCheckoutPhaseProvider(BasicServiceCheckoutPhaseProvider):
    '''
    Atribui a fase CieloCheckoutPhase à forma de pagamento CieloPaymentProcessor
    '''
    phase_class = CieloCheckoutPhase
    service_provider_class = CieloPaymentProcessor
