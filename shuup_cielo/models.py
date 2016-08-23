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

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.http.response import HttpResponseRedirect
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from enumfields import EnumIntegerField
import iso8601

from cielo_webservice.models import Comercial
from cielo_webservice.request import CieloRequest
from shuup.core.fields import MoneyValueField
from shuup.core.models import PaymentProcessor, ServiceChoice
from shuup.core.models._service_base import ServiceBehaviorComponent, ServiceCost
from shuup.core.models._shops import Shop
from shuup.utils.analog import LogEntryKind
from shuup.utils.excs import Problem
from shuup.utils.properties import MoneyProperty
from shuup_cielo.constants import (
    CIELO_AUTHORIZATION_TYPE_CHOICES, CIELO_DECIMAL_PRECISION, CIELO_PRODUCT_CHOICES,
    CIELO_SERVICE_CREDIT, CIELO_SERVICE_DEBIT, CieloAuthorizationType, CieloTransactionStatus,
    INTEREST_TYPE_CHOICES, InterestType
)
from shuup_cielo.objects import CIELO_ORDER_TRANSACTION_ID_KEY, CIELO_TRANSACTION_ID_KEY
from shuup_cielo.utils import decimal_to_int_cents, InstallmentCalculator, safe_int

logger = logging.getLogger(__name__)


class CieloPaymentProcessor(PaymentProcessor):
    '''
    Processador de pagamento Cielo
    '''

    class Meta:
        verbose_name = _('Cielo')
        verbose_name_plural = _('Cielo')

    def get_service_choices(self):
        return [
            ServiceChoice(CIELO_SERVICE_CREDIT, _('Credit card')),
            ServiceChoice(CIELO_SERVICE_DEBIT, _('Debit card')),
        ]

    def create_service(self, choice_identifier, **kwargs):
        service = super(CieloPaymentProcessor, self).create_service(choice_identifier, **kwargs)
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

        cielo_transaction = CieloTransaction.objects.filter(
            pk=order.payment_data.get(CIELO_TRANSACTION_ID_KEY)
        ).first()

        cielo_order = CieloOrderTransaction.objects.filter(
            pk=order.payment_data.get(CIELO_ORDER_TRANSACTION_ID_KEY)
        ).first()

        if not cielo_order or not cielo_transaction:
            order.set_canceled()
            order.add_log_entry(_('No payment identified.'), kind=LogEntryKind.ERROR)
            raise Problem(_('No payment identified.'), title=_('Order cancelled'))

        # faz as amarrações
        cielo_order.order = order
        cielo_order.save()

        return HttpResponseRedirect(urls.return_url)

    def process_payment_return_request(self, service, order, request):
        # limpa os dados da sessão
        request.cielo.clear()


@python_2_unicode_compatible
class CieloOrderTransaction(models.Model):
    """
    A sequence that is used as a order number before the real Order is created
    This is necessary because the transactions is made before the order is placed.
    """
    order = models.ForeignKey('shuup.Order',
                              related_name='cielo_transactions',
                              on_delete=models.CASCADE,
                              verbose_name=_('Order'),
                              null=True, default=None)

    class Meta:
        verbose_name = _('Cielo pre-order transaction')
        verbose_name_plural = _('Cielo pre-order transactions')

    def __str__(self):
        return "CieloOrder {0} for order ID {1}".format(self.id, self.order_id)


@python_2_unicode_compatible
class CieloTransaction(models.Model):
    TIMEOUT_SECONDS = 5

    shop = models.ForeignKey(Shop, verbose_name=_("shop"))
    order_transaction = models.OneToOneField(CieloOrderTransaction,
                                             related_name="transaction",
                                             verbose_name=_("Cielo Order"))
    tid = models.CharField(_('Transaction ID'), max_length=50)
    status = EnumIntegerField(CieloTransactionStatus,
                              verbose_name=_('Transaction status'),
                              default=CieloTransactionStatus.NotCreated,
                              blank=True)
    creation_date = models.DateTimeField(_('Creation date'), auto_now_add=True)
    last_update = models.DateTimeField(_('Last update'), auto_now=True)

    cc_holder = models.CharField(_('Card holder'), max_length=50)
    cc_brand = models.CharField(_('Card brand'), max_length=30)
    installments = models.PositiveSmallIntegerField(_('Installments'), default=1)
    cc_product = models.CharField(_('Product'), max_length=30, choices=CIELO_PRODUCT_CHOICES)

    total = MoneyProperty('total_value', 'order_transaction.order.currency')
    total_captured = MoneyProperty('total_captured_value', 'order_transaction.order.currency')
    total_reversed = MoneyProperty('total_reversed_value', 'order_transaction.order.currency')
    intereset = MoneyProperty('interest_value', 'order_transaction.order.currency')

    total_value = MoneyValueField(editable=False, verbose_name=_('transaction total'), default=0)
    total_captured_value = MoneyValueField(editable=True, verbose_name=_('total captured'), default=0)
    total_reversed_value = MoneyValueField(editable=True, verbose_name=_('total reversed'), default=0)
    interest_value = MoneyValueField(editable=False, verbose_name=_('interest amount'), default=0)

    authorization_lr = models.CharField(_('Authorization LR code'), max_length=2, blank=True)
    authorization_nsu = models.CharField(_('Authorization NSU'), max_length=50, blank=True, null=True)
    authorization_date = models.DateTimeField(_('Authorization date'), null=True, blank=True)

    authentication_eci = models.SmallIntegerField(_('ECI security level'), null=True, default=0)
    authentication_date = models.DateTimeField(_('Authentication date'), null=True, blank=True)

    international = models.BooleanField(_('International transaction'), default=False)

    class Meta:
        verbose_name = _('Cielo 1.5 transaction')
        verbose_name_plural = _('Cielo 1.5 transactions')

    def __str__(self):
        return "CieloTransaction TID={0}".format(self.tid)

    def _get_comercial(self):
        cielo_config = self.shop.cielo_config
        return Comercial(numero=safe_int(cielo_config.ec_num), chave=cielo_config.ec_key)

    def _get_cielo_request(self):
        return CieloRequest(sandbox=self.shop.cielo_config.sandbox)

    def refresh(self):
        '''
        Updates this transaction info with Cielo server

        :return: wheter the synchronization was successful
        '''
        
        # consuta a transação
        cielo_request = self._get_cielo_request()

        try:
            response_transaction = cielo_request.consultar(tid=self.tid,
                                                           comercial=self._get_comercial())
            self._update_from_transaction(response_transaction)
            return True

        except:
            logger.exception(_('Fail to update Cielo transation info'))

        return False

    def _update_from_transaction(self, response_transaction):
        if response_transaction.status:
            self.status = response_transaction.status

        if response_transaction.autorizacao:
            self.authorization_lr = response_transaction.autorizacao.lr
            self.authorization_nsu = response_transaction.autorizacao.nsu
            self.authorization_date = iso8601.parse_date(response_transaction.autorizacao.data_hora)
            self.international = (response_transaction.autorizacao.lr == "11")

        if response_transaction.autenticacao:
            self.authentication_eci = response_transaction.autenticacao.eci
            self.authentication_date = iso8601.parse_date(response_transaction.autenticacao.data_hora)

        if response_transaction.captura:
            self.total_captured_value = Decimal(response_transaction.captura.valor / 100.0)

        if response_transaction.cancelamento:
            self.total_reversed_value = Decimal(response_transaction.cancelamento.valor / 100.0)

        self.save()

    def capture(self, amount):
        '''
        Captures a total or partial amout of this transaction
        :type: amount: decimal.Decimal
        '''

        cielo_request = self._get_cielo_request()
        response_transaction = cielo_request.capturar(tid=self.tid,
                                                      comercial=self._get_comercial(),
                                                      valor=decimal_to_int_cents(amount))
        self._update_from_transaction(response_transaction)

    def safe_cancel(self, amount):
        """
        Safe transaction cancel (try, catch enclosed)
        :return: success or not
        :rtype: bool
        """
        try:
            self.cancel(amount)
            return True
        except:
            logger.exception(_("Failed to cancel transaction {0}").format(self.tid))
            return False

    def cancel(self, amount):
        '''
        Cancel a total or partial amout of this transaction
        :type: amount: decimal.Decimal
        '''
        cielo_request = self._get_cielo_request()
        response_transaction = cielo_request.cancelar(tid=self.tid,
                                                      comercial=self._get_comercial(),
                                                      valor=decimal_to_int_cents(amount))
        self._update_from_transaction(response_transaction)


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

    def __init__(self, installment_total_amount, cielo_config):
        self.installment_total_amount = installment_total_amount
        self.max_installments = cielo_config.max_installments
        self.installments_without_interest = cielo_config.installments_without_interest
        self.interest_type = cielo_config.interest_type
        self.interest_rate = cielo_config.interest_rate
        self.min_installment_amount = cielo_config.min_installment_amount

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
            if installment <= self.installments_without_interest or self.interest_rate <= Decimal(0):

                installment_amount = self.installment_total_amount / installment

            elif self.interest_type == InterestType.Simple:
                # juros simples
                installments_total, installment_amount = InstallmentCalculator.simple_interest(
                    self.installment_total_amount, installment, self.interest_rate
                )

            else:
                # PRICE tabale
                installments_total, installment_amount = InstallmentCalculator.price_interest(
                    self.installment_total_amount, installment, self.interest_rate
                )

            # o valor da parcela deve ser maior que o mínimo
            if installment_amount >= self.min_installment_amount:
                interest_total = installments_total - self.installment_total_amount

                installments.append(
                    (int(installment),
                     Decimal(installment_amount).quantize(CIELO_DECIMAL_PRECISION),
                     Decimal(installments_total).quantize(CIELO_DECIMAL_PRECISION),
                     Decimal(interest_total).quantize(CIELO_DECIMAL_PRECISION))
                )

        return sorted(installments, key=lambda x: x[0])


class CieloConfig(models.Model):
    MAX_INSTALLMENTS = 12
    shop = models.OneToOneField(Shop, verbose_name=_("Shop"), related_name="cielo_config")

    ec_num = models.CharField(_("Affiliation number"), max_length=20)
    ec_key = models.CharField(_("Affiliation secret key"), max_length=100)

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
        verbose_name = _('cielo configuration')
        verbose_name_plural = _('cielo configurations')

    def __str__(self):  # pragma: no cover
        return _('Cielo configuration for {0}').format(self.shop)


class CieloInstallmentInterestBehaviorComponent(ServiceBehaviorComponent):
    name = _('Cielo installment interest')
    help_text = _('Captures and returns the total interest amount of an installment')

    def get_costs(self, service, source):
        interest_total = source.create_price(0)
        description = None

        if service.choice_identifier == CIELO_SERVICE_CREDIT and source.request.cielo.transaction and \
                source.request.cielo.transaction.interest_value > Decimal(0):
            interest_total = source.create_price(source.request.cielo.transaction.interest_value)
            description = _('installment interest for {0}x').format(source.request.cielo.transaction.installments)

        yield ServiceCost(interest_total, description)


class DiscountPercentageBehaviorComponent(ServiceBehaviorComponent):
    percentage = models.DecimalField(verbose_name=_('Discount percentage'),
                                     decimal_places=2,
                                     max_digits=5)
    name = _('Discount percentage')
    help_text = _("Applies a discount percentage over the basket's products")

    def get_costs(self, service, source):
        products_total = sum([product.price.value for product in source.get_product_lines()])
        description = _('products discount {0:.2f}%').format(-self.percentage)
        discount_amoumt = source.create_price(products_total * ((-self.percentage) / Decimal(100.0)))
        yield ServiceCost(discount_amoumt, description)
