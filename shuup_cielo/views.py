# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from decimal import Decimal
import logging
import time

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http.response import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.utils.formats import localize
from django.utils.timezone import now
from django.utils.translation import ugettext as _p
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import View
from django.views.generic.edit import BaseFormView

from cielo_webservice.exceptions import CieloRequestError
from cielo_webservice.models import Cartao, Comercial, Pagamento, Pedido, Transacao
from cielo_webservice.request import CieloRequest
from shuup.utils.i18n import format_money
from shuup.utils.importing import cached_load, load
from shuup_cielo.constants import (
    CIELO_AUTHORIZED_STATUSES, CIELO_SERVICE_CREDIT, CIELO_UKNOWN_ERROR_MSG, CieloAuthorizationCode,
    CieloProduct, CieloProductMatrix, CieloTransactionStatus,
    INSTALLMENT_CHOICE_WITH_INTEREST_STRING, INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING
)
from shuup_cielo.forms import CieloPaymentForm
from shuup_cielo.models import CieloOrderTransaction, CieloTransaction, InstallmentContext
from shuup_cielo.utils import decimal_to_int_cents, safe_int
from shuup.front.checkout._storage import CheckoutPhaseStorage

logger = logging.getLogger(__name__)


def _configure_basket(request):
    """
    Search for some needed keys in the checkout phases storages
    """

    # (src key, destination key) pair
    search_keys = [
        ('payment_method_id', 'payment_method_id'),
        ('shipping_method_id', 'shipping_method_id'),
        ('shipping', 'shipping_address'),
        ('shipping_extra', 'shipping_address_extra'),
        ('payment', 'payment_address'),
        ('payment_extra', 'payment_address_extra'),
    ]

    for phase in cached_load("SHUUP_CHECKOUT_VIEW_SPEC").phase_specs:
        phase_class = load(phase)

        storage = CheckoutPhaseStorage(request, phase_class.identifier)

        for key, dst_key in search_keys:
            value = storage.get(key)

            # key found, set it to request.basket on dst_key
            if value:
                setattr(request.basket, dst_key, value)


class GetInstallmentsOptionsView(View):
    """
    Calculate and returns installment options for the current basket
    """

    def get(self, request, *args, **kwargs):
        cc_brand = request.GET.get("cc_brand", "").lower()

        if not cc_brand:
            return HttpResponseBadRequest()

        if not hasattr(request.shop, "cielo_config"):
            logger.error("CieloConfig not configured for {0} shop".format(request.shop))
            return HttpResponseBadRequest()

        try:
            # populate the basket with all the checkout stuff
            _configure_basket(request)

            basket_total = request.basket.taxful_total_price.value
        except:
            logger.exception("Basket total is not valid")
            return HttpResponseBadRequest()

        installments = []

        FALLBACK_INSTALLMENT = {
            "number": 1,
            "name": INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING.format(
                1,
                format_money(request.basket.create_price(basket_total)),
                format_money(request.basket.create_price(basket_total)),
                localize(Decimal())
            )
        }

        # if it is a credit card service and the brand allows installments..
        if CieloProductMatrix.get(cc_brand, {}).get(CieloProduct.InstallmentCredit):

            try:
                context = InstallmentContext(basket_total, request.shop.cielo_config)
                interest_rate = request.shop.cielo_config.interest_rate

                for choice in context.get_intallments_choices():

                    # if installment has interest
                    if choice[3] > 0:
                        name = INSTALLMENT_CHOICE_WITH_INTEREST_STRING.format(
                            choice[0],
                            format_money(request.basket.create_price(choice[1])),
                            format_money(request.basket.create_price(choice[2])),
                            localize(interest_rate)
                        )
                    else:
                        name = INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING.format(
                            choice[0],
                            format_money(request.basket.create_price(choice[1])),
                            format_money(request.basket.create_price(choice[2]))
                        )

                    installments.append({"number": choice[0], "name": name})

            except:
                logger.exception("Failed to calculate installments for basket {0}".format(request.basket))

        if len(installments) == 0:
            installments.append(FALLBACK_INSTALLMENT)

        return JsonResponse({"installments": installments})


class TransactionView(BaseFormView):
    """
    Make a Cielo transaction
    """
    form_class = CieloPaymentForm

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(context or {}, **response_kwargs)

    def form_valid(self, form):
        # verifica se existe alguma transação pendente na sessão
        # se sim, cancela a autorização antiga para fazer uma nova
        if self.request.cielo.transaction:
            try:
                self.request.cielo.transaction.safe_cancel(self.request.cielo.transaction.total_value)
            except:
                logger.exception(_("Failed to cancel old Cielo transaction"))

        # populate the basket with all the checkout stuff
        _configure_basket(self.request)
        order_total = self.request.basket.taxful_total_price.value
        service = self.request.basket.payment_method.choice_identifier

        cc_info = form.cleaned_data
        transaction_total = order_total
        interest_amount = Decimal()
        installments = safe_int(cc_info['installments'])

        cielo_config = self.request.shop.cielo_config

        produto = CieloProduct.Credit

        if service == CIELO_SERVICE_CREDIT:
            if installments > 1:
                installment_choices = InstallmentContext(order_total, cielo_config).get_intallments_choices()

                # verifica se o número da parcela existe nas opções
                if installments <= len(installment_choices):
                    produto = CieloProduct.InstallmentCredit

                    # obtém o valor da transação de acordo com a parcela escolhida
                    transaction_total = installment_choices[installments-1][2]
                    interest_amount = installment_choices[installments-1][3]
                else:
                    installments = 1

        else:
            # debito
            produto = CieloProduct.Debit
            installments = 1

        cielo_order = CieloOrderTransaction.objects.create()

        comercial = Comercial(numero=safe_int(cielo_config.ec_num), chave=cielo_config.ec_key)

        cartao = Cartao(numero=safe_int(cc_info['cc_number']),
                        validade=safe_int("{0}{1}".format(cc_info['cc_valid_year'], cc_info['cc_valid_month'])),
                        indicador=1,  # sempre sera necessario o digito verificador
                        codigo_seguranca=safe_int(cc_info['cc_security_code']),
                        nome_portador=cc_info['cc_holder'])

        pedido = Pedido(numero="{0}".format(cielo_order.pk),
                        valor=decimal_to_int_cents(transaction_total),
                        moeda=986,  # Fixo
                        data_hora=now().isoformat())

        pagamento = Pagamento(bandeira=cc_info['cc_brand'],
                              produto=produto,
                              parcelas=installments)

        return_url = self.request.build_absolute_uri(
            reverse("shuup:cielo_transaction_return", kwargs={"cielo_order_pk": cielo_order.id})
        )

        transacao = Transacao(comercial=comercial,
                              cartao=cartao,
                              pedido=pedido,
                              pagamento=pagamento,
                              autorizar=cielo_config.authorization_mode,
                              capturar=cielo_config.auto_capture,
                              url_retorno=return_url)

        cielo_request = CieloRequest(sandbox=cielo_config.sandbox)

        # base response data
        response_data = {"success": False}
        cielo_transaction = None

        try:
            response_transaction = cielo_request.autorizar(transacao=transacao)

            cielo_transaction = CieloTransaction.objects.create(shop=self.request.shop,
                                                                order_transaction=cielo_order,
                                                                tid=response_transaction.tid,
                                                                status=response_transaction.status,
                                                                total_value=transaction_total,
                                                                cc_holder=cc_info['cc_holder'],
                                                                cc_brand=cc_info['cc_brand'],
                                                                cc_product=produto,
                                                                installments=installments,
                                                                interest_value=interest_amount)

            # se existe uma URL para autenticacao, vamos redirecionar primeiro
            if response_transaction.url_autenticacao:
                response_data["success"] = True
                response_data["redirect_url"] = response_transaction.url_autenticacao

            # transação autorizada, vamos para a página de retorno para
            # efetivar
            elif response_transaction.autorizacao:

                if response_transaction.autorizacao.lr in CIELO_AUTHORIZED_STATUSES:
                    response_data["success"] = True
                    response_data["redirect_url"] = return_url

                else:
                    response_data["success"] = False
                    error = _p("Transaction not authorized: {0}").format(
                        CieloAuthorizationCode.get(
                            response_transaction.autorizacao.lr, {}
                        ).get('msg', CIELO_UKNOWN_ERROR_MSG)
                    )
                    response_data["error"] = error

            else:
                response_data["success"] = False
                response_data["error"] = _p("Transaction not authorized: {0}").format(CIELO_UKNOWN_ERROR_MSG)

        except CieloRequestError:
            response_data["success"] = False
            response_data["error"] = _p("Internal error")
            logger.exception(_("Cielo transaction error."))

        else:
            self.request.cielo.set_order_transaction(cielo_order)
            self.request.cielo.set_transaction(cielo_transaction)
            self.request.cielo.commit()

        return self.render_to_response(response_data)

    def form_invalid(self, form):
        return self.render_to_response({
            'fields': form.errors,
            'form': form.non_field_errors()
        }, status=400)


class TransactionReturnView(View):

    def post(self, request, **kwargs):
        return self.handle_request(request, **kwargs)

    def get(self, request, **kwargs):
        return self.handle_request(request, **kwargs)

    def handle_request(self, request, **kwargs):
        cielo_order_pk = kwargs['cielo_order_pk']
        cielo_order = self.request.cielo.order_transaction
        cielo_transaction = self.request.cielo.transaction

        # dados da transação não existem na sessão, volta pro pagamento
        if not cielo_order or not cielo_transaction or not cielo_order.pk == safe_int(cielo_order_pk):
            self.request.cielo.rollback()
            self.request.cielo.clear()

            messages.error(request, _("Payment not identified. Old transactions were also cancelled."))
            return HttpResponseRedirect(reverse("shuup:checkout", kwargs={"phase": "payment"}))

        cielo_transaction.refresh()

        max_tries = 3
        tries = 0
        # aguarda uma transação mudar de estado -> de autenticando para qualquer outra coisa
        # pois ainda não temos o estado da autorização
        while cielo_transaction.status == CieloTransactionStatus.Authenticating and tries <= max_tries:
            cielo_transaction.refresh()
            tries = tries + 1
            time.sleep(0.1)

        # not authorized, clean data
        if cielo_transaction.authorization_lr not in CIELO_AUTHORIZED_STATUSES:
            messages.error(request, _("Transaction not authorized: {0}").format(
                CieloAuthorizationCode.get(cielo_transaction.authorization_lr, {}).get('msg', _("Unknown error"))
            ))

            self.request.cielo.rollback()
            self.request.cielo.clear()
            return HttpResponseRedirect(reverse("shuup:checkout", kwargs={"phase": "payment"}))

        # se tudo deu certo, vamos para o fim direto
        messages.success(request, _("Transaction authorized."))
        return HttpResponseRedirect(reverse("shuup:checkout", kwargs={"phase": "confirm"}))
