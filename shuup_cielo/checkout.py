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

from shuup_cielo.constants import (
    CIELO_CREDIT_CARD_INFO_KEY, CIELO_DEBIT_CARD_INFO_KEY, CIELO_INSTALLMENT_INFO_KEY,
    CIELO_SERVICE_CREDIT
)
from shuup_cielo.forms import CieloPaymentForm
from shuup_cielo.models import CieloWS15PaymentProcessor, InstallmentContext

from shuup.front.checkout import BasicServiceCheckoutPhaseProvider, CheckoutPhaseViewMixin

from django.core import signing
from django.utils.translation import ugettext_lazy as _
from django.views.generic.edit import FormView

logger = logging.getLogger(__name__)


class CieloCheckoutPhase(CheckoutPhaseViewMixin, FormView):
    template_name = 'cielo/checkout.jinja'
    identifier = 'cielo'
    title = _('Payment information')
    form_class = CieloPaymentForm

    def get_initial(self):
        initial = self.initial.copy()

        if self.storage.get(CIELO_CREDIT_CARD_INFO_KEY):
            cc_info = signing.loads(self.storage[CIELO_CREDIT_CARD_INFO_KEY])

            initial.update({
                'installments': cc_info['installments'],
                'cc_brand': '',
                'cc_holder': '',
                'cc_number': '',
                'cc_security_code': '',
                'cc_valid_year': '',
                'cc_valid_month': '',
            })

        elif self.storage.get(CIELO_DEBIT_CARD_INFO_KEY):
            cc_info = signing.loads(self.storage[CIELO_DEBIT_CARD_INFO_KEY])

            initial.update({
                'cc_brand': '',
                'cc_holder': '',
                'cc_number': '',
                'cc_security_code': '',
                'cc_valid_year': '',
                'cc_valid_month': '',
            })

        return initial

    def get_form_kwargs(self):
        kwargs = super(CieloCheckoutPhase, self).get_form_kwargs()

        if self.request.basket.payment_method_id:
            payment_method = self.request.basket.payment_method

            # IMPORTANT: !!!
            # Calcula o total do custo do método de pagamento para ser descontado do total do parcelamento
            # O total desta forma de pagamento será o valor adicional do juros do parcelamento,
            # sendo assim este valor deve ser desconsiderado na hora de calular as parcelas
            payment_method_price = sum(
                [line.price.value for line in self.request.basket._compute_payment_method_lines()]
            )

            # para fazer o calculo das parcelas, precisamos montar o contexto
            # contendo o valor total do carrinho e também as constraints
            # vamos ter pacelas se for o serviço de cartão de crédito e for o processador da Cielo
            if payment_method.choice_identifier == CIELO_SERVICE_CREDIT:
                context = InstallmentContext(
                    (self.request.basket.taxful_total_price.value - payment_method_price),
                    payment_method.payment_processor
                )

                kwargs['installment_context'] = context

            kwargs['service'] = payment_method.choice_identifier

        kwargs['currency'] = self.request.basket.currency
        return kwargs

    def is_valid(self):

        # verifica se o serviço é credito ou débito
        if self.request.basket.payment_method.choice_identifier == CIELO_SERVICE_CREDIT:
            # temos uma informação de parcelamento.. vamos conferir se o valor
            # do parcelado bate com o valor do pedido..
            # se não bater, invalidamos as informações do cartão do cartão e parcelamento
            if self.storage.get(CIELO_INSTALLMENT_INFO_KEY):
                payment_method_price = sum([line.price.value for line in self.request.basket._compute_payment_method_lines()])

                # houve acréscimo da forma de pagamento - juros no parcelamento
                if payment_method_price:
                    basket_total = self.request.basket.taxful_total_price.value
                    installments_total = Decimal(self.storage['cielows15_installment']['installments_total'])

                    # Ops, a diferença entre o total das parcelas e do valor do carrinho ultrapassa 1 centavo
                    # vamos invalidar tudo...
                    if abs(installments_total - basket_total) > 0.01:
                        self.storage[CIELO_CREDIT_CARD_INFO_KEY] = None
                        self.storage[CIELO_INSTALLMENT_INFO_KEY] = None

            return not self.storage.get(CIELO_CREDIT_CARD_INFO_KEY) is None

        else:
            # cartão de débito
            return not self.storage.get(CIELO_DEBIT_CARD_INFO_KEY) is None

    def form_invalid(self, form):
        # limpa os dados do form - de acordo com a PCI
        data = form.data.copy()
        data['cc_number'] = ''
        data['cc_security_code'] = ''
        data['cc_valid_year'] = ''
        data['cc_valid_month'] = ''
        form.data = data
        return super(CieloCheckoutPhase, self).form_invalid(form)

    def form_valid(self, form):
        # nunca deixa os dados do formulário salvo
        clean_form = self.get_form_class()()

        # salva temporariamente os dados do cartão e o valor total do pedido na sessão
        # FIXME: ver uma melhor maneira de armazenar temporariamente estes dados aqui
        # pois pode ser um problema de segurança se a SECRET_KEY vazar
        # (não só isso mas todo o sistema estará comprometido)
        # e é por isso que no deploy a SECRET_KEY deveria ser lida de um arquivo
        # na qual apenas o usuário do servidor http tenha acesso (leitura e escrita)
        cc_info = signing.dumps(form.cleaned_data)

        # verifica se o serviço é credito ou débito
        if self.request.basket.payment_method.choice_identifier == CIELO_SERVICE_CREDIT:

            # Obtém a forma de parcelamento escolhida e salva ela no storage
            # Essa informação ficará salva nas informações extra do pedido em `payment_data`
            # Os dados serão utilizados especialmente para adicionar uma OrderLine
            # no pedido para que seja somada no total
            # Pode ser que o `installment_context` seja nulo
            selected_installment = None

            if form.installment_context:
                for installment_choice in form.installment_context.get_intallments_choices():
                    if installment_choice[0] == int(form.cleaned_data['installments']):
                        selected_installment = {
                            "installment": installment_choice[0],
                            "installment_amount": installment_choice[1],
                            "installments_total": installment_choice[2],
                            "interest_total": installment_choice[3],
                        }
                        break

            self.storage[CIELO_CREDIT_CARD_INFO_KEY] = cc_info
            self.storage[CIELO_INSTALLMENT_INFO_KEY] = selected_installment
        else:
            self.storage[CIELO_DEBIT_CARD_INFO_KEY] = cc_info

        return super(CieloCheckoutPhase, self).form_valid(clean_form)

    def process(self):
        # transfere os dados do storage para o basket
        self.request.basket.payment_data.update({CIELO_CREDIT_CARD_INFO_KEY: self.storage.get(CIELO_CREDIT_CARD_INFO_KEY),
                                                 CIELO_DEBIT_CARD_INFO_KEY: self.storage.get(CIELO_DEBIT_CARD_INFO_KEY),
                                                 CIELO_INSTALLMENT_INFO_KEY: self.storage.get(CIELO_INSTALLMENT_INFO_KEY)})
        self.request.basket.save()


class CieloCheckoutPhaseProvider(BasicServiceCheckoutPhaseProvider):
    '''
    Atribui a fase CieloCheckoutPhase à forma de pagamento CieloWS15PaymentProcessor
    '''
    phase_class = CieloCheckoutPhase
    service_provider_class = CieloWS15PaymentProcessor
