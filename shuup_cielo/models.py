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

from enumfields import EnumIntegerField
import iso8601
import six

from shuup_cielo.constants import (
    CIELO_AUTHORIZATION_TYPE_CHOICES, CIELO_CREDIT_CARD_INFO_KEY, CIELO_DEBIT_CARD_INFO_KEY,
    CIELO_INSTALLMENT_INFO_KEY, CIELO_PRODUCT_CHOICES, CIELO_SERVICE_CREDIT, CIELO_SERVICE_DEBIT,
    CIELO_TID_INFO_KEY, CieloAuthorizationType, CieloProduct, CieloTransactionStatus,
    INTEREST_TYPE_CHOICES, InterestType
)
from shuup_cielo.utils import decimal_to_int_cents, InstallmentCalculator, safe_int

from django.core import signing
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.http.response import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _

from cielo_webservice.exceptions import CieloRequestError
from cielo_webservice.models import Cartao, Comercial, Pagamento, Pedido, Transacao
from cielo_webservice.request import CieloRequest

from shuup.core.fields import MoneyValueField
from shuup.core.models import PaymentProcessor, ServiceChoice
from shuup.core.models._order_lines import OrderLineType
from shuup.core.models._service_base import ServiceBehaviorComponent, ServiceCost
from shuup.utils.analog import LogEntryKind
from shuup.utils.excs import Problem
from shuup.utils.properties import MoneyProperty

logger = logging.getLogger(__name__)


class CieloWS15PaymentProcessor(PaymentProcessor):
    '''
    Processador de pagamento Cielo WS versão 1.5
    '''

    MAX_INSTALLMENTS = 18

    ec_num = models.CharField(_("Cielo's affiliation number"), max_length=20)
    ec_key = models.CharField(_("Cielo's affiliation secret key"), max_length=100)

    auto_capture = models.BooleanField(_('Auto capture transactions'),
                                       default=False,
                                       help_text=_('Enable this to capture transactions right after '
                                                   'they get approved.'))

    authorization_mode = models.SmallIntegerField(_('Authorization mode'),
                                                  default=CieloAuthorizationType.IfAuthenticatedOrNot,
                                                  choices=CIELO_AUTHORIZATION_TYPE_CHOICES,
                                                  help_text=_('Select the authroization type for credit cards.'))

    max_installments = models.PositiveSmallIntegerField(_('Maximum installments number'),
                                                        default=1,
                                                        validators=[
                                                            MinValueValidator(1),
                                                            MaxValueValidator(MAX_INSTALLMENTS)
                                                        ])

    installments_without_interest = models.PositiveSmallIntegerField(_('Installments without interest'),
                                                                     default=1,
                                                                     validators=[
                                                                        MinValueValidator(1),
                                                                        MaxValueValidator(MAX_INSTALLMENTS)
                                                                     ],
                                                                     help_text=_('How many installments '
                                                                                 'will have no interest applied.'))

    interest_type = models.CharField(_('Interest type'),
                                     max_length=1,
                                     default=InterestType.Price,
                                     choices=INTEREST_TYPE_CHOICES)

    interest_rate = models.DecimalField(_('Interest rate'),
                                        max_digits=5,
                                        decimal_places=2,
                                        default=Decimal(0),
                                        validators=[MinValueValidator(Decimal(0))])

    min_installment_amount = models.DecimalField(_('Minimum installment amount'),
                                                 max_digits=9,
                                                 decimal_places=2,
                                                 default=Decimal(5),
                                                 validators=[MinValueValidator(Decimal(5))])

    sandbox = models.BooleanField(_('Sandbox mode'),
                                  default=False,
                                  help_text=_('Enable this to activate Developer mode (test mode).'))

    class Meta:
        verbose_name = _('Cielo Webservice v1.5')
        verbose_name_plural = _('Cielo Webservice v1.5')

    def get_service_choices(self):
        return [
            ServiceChoice(CIELO_SERVICE_CREDIT, _('Credit card')),
            ServiceChoice(CIELO_SERVICE_DEBIT, _('Debit card')),
        ]

    def create_service(self, choice_identifier, **kwargs):
        service = super(CieloWS15PaymentProcessor, self).create_service(choice_identifier, **kwargs)
        service.behavior_components.add(CieloInstallmentInterestBehaviorComponent.objects.create())
        return service

    def get_payment_process_response(self, service, order, urls):
        """
        Get payment process response for given order.

        :type service: shuup.core.models.PaymentMethod
        :type order: shuup.core.models.Order
        :type urls: PaymentUrls
        :rtype: django.http.HttpResponse|None
        """

        # TODO: gerar um token para o cartão e salvar
        # para que seja possível efetuar retentativas
        # de uma maneira mais fácil

        if not order.payment_data:
            order.set_canceled()
            order.add_log_entry(_('Payment data is None when it was needed to proccess a Cielo transaction'), kind=LogEntryKind.ERROR)
            raise Problem(_('No payment identified.'), title=_('Order cancelled'))

        # obtém os dados do cartão de acordo com o serviço
        if service.choice_identifier == CIELO_SERVICE_DEBIT:
            cc_info = signing.loads(order.payment_data[CIELO_DEBIT_CARD_INFO_KEY])
        else:
            cc_info = signing.loads(order.payment_data[CIELO_CREDIT_CARD_INFO_KEY])

        # obtém o total adicional gerado por causa do método do pagamento
        # aqui o valor deve ser o total do juros gerado pelo parcelamento, se houver
        payment_method_total = sum([line.price.value for line in order.lines.filter(type=OrderLineType.PAYMENT)])

        # obtém os dados de parcelamento, se disponível
        selected_installment = order.payment_data.get(CIELO_INSTALLMENT_INFO_KEY)

        # se houve parcelamento, confere o valor total do pedido com o total do parcelado
        # DEVEM SER EXATAMENTE OS MESMOS, caso contrário vamos parcelar algo com valor incorreto
        if selected_installment:
            total_difference = abs(Decimal(selected_installment['interest_total']) - payment_method_total)

            if total_difference > 0.01:
                order.set_canceled()
                order.add_log_entry(_('Installment interest total is different from the order payment method total.'), kind=LogEntryKind.ERROR)
                raise Problem(_('Installment interest total is different from the order payment method total!'),
                                title=_('Order cancelled'))

        # pré-calcula
        order_total = order.taxful_total_price.value

        comercial = Comercial(numero=safe_int(self.ec_num), chave=self.ec_key)

        cartao = Cartao(numero=safe_int(cc_info['cc_number']),
                        validade=safe_int("{0}{1}".format(cc_info['cc_valid_year'], cc_info['cc_valid_month'])),
                        indicador=1,  # sempre será necessário o digito verificador
                        codigo_seguranca=safe_int(cc_info['cc_security_code']),
                        nome_portador=cc_info['cc_holder'])

        pedido = Pedido(numero="{0}".format(order.pk),
                        valor=decimal_to_int_cents(order_total),
                        moeda=986,  # Fixo
                        data_hora=order.order_date.isoformat())

        produto = CieloProduct.Credit
        installments = safe_int(cc_info['installments'])

        if service.choice_identifier == CIELO_SERVICE_CREDIT:
            if installments > 1:
                produto = CieloProduct.InstallmentCredit
        else:
            # debito
            produto = CieloProduct.Debit

        pagamento = Pagamento(bandeira=cc_info['cc_brand'],
                              produto=produto,
                              parcelas=installments)

        transacao = Transacao(comercial=comercial,
                              cartao=cartao,
                              pedido=pedido,
                              pagamento=pagamento,
                              autorizar=self.authorization_mode,
                              capturar=self.auto_capture,
                              url_retorno=urls.return_url)

        cielo_request = CieloRequest(sandbox=self.sandbox)

        try:
            response_transaction = cielo_request.autorizar(transacao=transacao)

            cielows15_transaction = CieloWS15Transaction.objects.create(order=order,
                                                                        tid=response_transaction.tid,
                                                                        status=response_transaction.status,
                                                                        total_value=order_total,
                                                                        cc_holder=cc_info['cc_holder'],
                                                                        cc_brand=cc_info['cc_brand'],
                                                                        cc_product=produto,
                                                                        installments=installments)

            if response_transaction.autorizacao:
                cielows15_transaction.authorization_lr = response_transaction.autorizacao.lr
                cielows15_transaction.authorization_nsu = response_transaction.autorizacao.nsu
                cielows15_transaction.authorization_date = iso8601.parse_date(response_transaction.autorizacao.data_hora)

            if response_transaction.autenticacao:
                cielows15_transaction.authentication_eci = response_transaction.autenticacao.eci
                cielows15_transaction.authentication_date = iso8601.parse_date(response_transaction.autenticacao.data_hora)

            cielows15_transaction.save()

            # salva a TID no pedido e remove os dados do cartão do pedido
            order.payment_data[CIELO_TID_INFO_KEY] = response_transaction.tid
            order.payment_data[CIELO_CREDIT_CARD_INFO_KEY] = None
            order.payment_data[CIELO_DEBIT_CARD_INFO_KEY] = None
            order.save()

            # se existe uma URL para autenticacao, vamos redirecionar
            if response_transaction.url_autenticacao:
                return HttpResponseRedirect(response_transaction.url_autenticacao)

            # Tudo certo, vamos pra frente
            return HttpResponseRedirect(urls.return_url)

        except CieloRequestError as err:
            error_str = "{0}".format(err)
            order.add_log_entry(_("Cielo transaction failed: {0}").format(error_str), kind=LogEntryKind.ERROR)
            err_code = safe_int(error_str.split("-")[0].strip())

            if err_code == 17:  # Código de segurança inválido
                error = _('Invalid security code.')
            else:
                error = _('Unknown error.')

            # TODO: Quando o Shuup possibilitar a retentativa de pagamento
            # não cancelar o pedido e sim informar o usuário par atentar novamente
            # ou redirectionar para uma página especial da Cielo para retentar
            order.set_canceled()
            raise Problem(error, title=_('Payment failed'))

        return HttpResponseRedirect(urls.cancel_url)

    def process_payment_return_request(self, service, order, request):
        """
        Process payment return request for given order.

        :type service: shuup.core.models.PaymentMethod
        :type order: shuup.core.models.Order
        :type request: django.http.HttpRequest
        :rtype: None
        """
        tid = order.payment_data.get(CIELO_TID_INFO_KEY)

        try:
            cielows15_transaction = CieloWS15Transaction.objects.get(order=order, tid=tid)
        except CieloWS15Transaction.DoesNotExist:
            order.set_canceled()
            raise Problem(_('Payment not identified.'), title=_('Order cancelled'))

        cielows15_transaction.refresh()

        # Apenas marca como pago se a transação já foi capturada ou autorizada
        # em qualquer outro estado, apena será possível
        # concluir o pedido quando o pagamento for autorizado
        if cielows15_transaction.status in (CieloTransactionStatus.Captured,
                                            CieloTransactionStatus.Authorized):
            order.create_payment(
                order.taxful_total_price,
                payment_identifier=tid
            )

        # remove informação sigilosa
        order.payment_data[CIELO_CREDIT_CARD_INFO_KEY] = None
        order.payment_data[CIELO_DEBIT_CARD_INFO_KEY] = None
        order.save()


class CieloWS15Transaction(models.Model):
    order = models.ForeignKey('shuup.Order',
                              related_name='cielows15_transactions',
                              on_delete=models.CASCADE,
                              verbose_name=_('Order'))

    tid = models.CharField(_('Transaction ID'), max_length=50)
    status = EnumIntegerField(CieloTransactionStatus,
                              verbose_name=_('Transaction status'),
                              default=CieloTransactionStatus.Created,
                              blank=True)
    creation_date = models.DateTimeField(_('Creation date'), auto_now_add=True)
    last_update = models.DateTimeField(_('Last update'), auto_now=True)

    cc_holder = models.CharField(_('Card holder'), max_length=50)
    cc_brand = models.CharField(_('Card brand'), max_length=30)
    installments = models.PositiveSmallIntegerField(_('Installments'), default=1)
    cc_product = models.CharField(_('Product'), max_length=30, choices=CIELO_PRODUCT_CHOICES)

    total = MoneyProperty('total_value', 'order.currency')
    total_captured = MoneyProperty('total_captured_value', 'order.currency')
    total_reversed = MoneyProperty('total_reversed_value', 'order.currency')

    total_value = MoneyValueField(editable=False, verbose_name=_('transaction total'), default=0)
    total_captured_value = MoneyValueField(editable=True, verbose_name=_('total captured'), default=0)
    total_reversed_value = MoneyValueField(editable=True, verbose_name=_('total reversed'), default=0)

    authorization_lr = models.CharField(_('Authorization LR code'), max_length=2, blank=True)
    authorization_nsu = models.CharField(_('Authorization NSU'), max_length=50, blank=True, null=True)
    authorization_date = models.DateTimeField(_('Authorization date'), null=True, blank=True)

    authentication_eci = models.SmallIntegerField(_('ECI security level'), null=True, default=0)
    authentication_date = models.DateTimeField(_('Authentication date'), null=True, blank=True)

    class Meta:
        verbose_name = _('Cielo 1.5 transaction')
        verbose_name_plural = _('Cielo 1.5 transactions')

    def _get_comercial(self):
        return Comercial(numero=safe_int(self.order.payment_method.payment_processor.ec_num),
                         chave=self.order.payment_method.payment_processor.ec_key)

    def _get_cielo_request(self):
        return CieloRequest(sandbox=self.order.payment_method.payment_processor.sandbox)

    def refresh(self):
        '''
        Updates this transaction info with Cielo server

        :return: wheter the synchronization was successful
        '''

        # consuta a transação
        cielo_request = self._get_cielo_request()

        try:
            response_transaction = cielo_request.consultar(tid=self.tid, comercial=self._get_comercial())

            # atualiza o status da transação
            self.status = response_transaction.status

            if response_transaction.autorizacao:
                self.authorization_lr = response_transaction.autorizacao.lr
                self.authorization_nsu = response_transaction.autorizacao.nsu
                self.authorization_date = iso8601.parse_date(response_transaction.autorizacao.data_hora)

            if response_transaction.autenticacao:
                self.authentication_eci = response_transaction.autenticacao.eci
                self.authentication_date = iso8601.parse_date(response_transaction.autenticacao.data_hora)

            if response_transaction.captura:
                self.total_captured_value = Decimal(response_transaction.captura.valor / 100.0)

            if response_transaction.cancelamento:
                self.total_reversed_value = Decimal(response_transaction.cancelamento.valor / 100.0)

            self.save()
            return True

        except:
            logger.exception(_('Fail to update Cielo transation info'))

        return False

    def capture(self, amount):
        '''
        Captures a total or partial amout of this transaction
        :type: amount: decimal.Decimal
        '''

        cielo_request = self._get_cielo_request()
        cielo_request.capturar(tid=self.tid,
                               comercial=self._get_comercial(),
                               valor=decimal_to_int_cents(amount))

    def cancel(self, amount):
        '''
        Cancel a total or partial amout of this transaction
        :type: amount: decimal.Decimal
        '''

        cielo_request = self._get_cielo_request()
        cielo_request.cancelar(tid=self.tid,
                               comercial=self._get_comercial(),
                               valor=decimal_to_int_cents(amount))


class InstallmentContext(object):
    '''
    Contexto para cálculo de parcelamento
    '''

    installment_total_amount = Decimal()
    max_installments = 1
    installments_without_interest = 1
    interest_type = InterestType.Price
    interest_rate = Decimal()
    min_installment_amount = Decimal()

    def __init__(self, installment_total_amount, payment_processor):
        self.installment_total_amount = installment_total_amount
        self.max_installments = payment_processor.max_installments
        self.installments_without_interest = payment_processor.installments_without_interest
        self.interest_type = payment_processor.interest_type
        self.interest_rate = payment_processor.interest_rate
        self.min_installment_amount = payment_processor.min_installment_amount

    def get_intallments_choices(self):
        '''
        Calculate all the possible installments for an installment context and intereset type

        Returns a sorted list of tuples in the following format:
            (installment number, installment amount, total with intereset, interest amount)

        '''
        installments = []

        for installment in range(1, self.max_installments + 1):
            installment_amount = Decimal()
            installments_total = Decimal(self.installment_total_amount)

            # parcela sem juros
            if installment <= self.installments_without_interest:

                installment_amount = self.installment_total_amount / installment

            elif self.interest_type == InterestType.Simple:
                # juros simples
                installments_total, installment_amount = InstallmentCalculator.simple_interest(
                                                            self.installment_total_amount,
                                                            installment,
                                                            self.interest_rate
                                                         )

            else:
                # PRICE tabale
                installments_total, installment_amount = InstallmentCalculator.price_interest(
                                                            self.installment_total_amount,
                                                            installment,
                                                            self.interest_rate
                                                         )

            # o valor da parcela deve ser maior que o mínimo
            if installment_amount >= self.min_installment_amount:
                interest_total = installments_total - self.installment_total_amount

                # precisão de 2 casas decimais apenas
                decimal_precision = Decimal('0.01')

                installments.append(
                    (int(installment),
                     Decimal(installment_amount).quantize(decimal_precision),
                     Decimal(installments_total).quantize(decimal_precision),
                     Decimal(interest_total).quantize(decimal_precision))
                )

        return sorted(installments, key=lambda x: x[0])


class CieloInstallmentInterestBehaviorComponent(ServiceBehaviorComponent):
    name = _('Cielo installment interest')
    help_text = _('Captures and returns the total interest amount of an installment')

    def get_costs(self, service, source):
        interest_total = source.create_price(0)
        description = None

        installment_info = source.payment_data.get(CIELO_INSTALLMENT_INFO_KEY)
        if installment_info:

            if installment_info['interest_total'] > 0.01:
                interest_total = source.create_price(installment_info['interest_total'])
                description = _('installment interest for {0}x').format(installment_info['installment'])

        yield ServiceCost(interest_total, description)
