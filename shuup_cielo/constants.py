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

from enumfields import Enum

from django.contrib.staticfiles.templatetags.staticfiles import static
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

# precisão de 2 casas decimais apenas
CIELO_DECIMAL_PRECISION = Decimal('0.01')

CIELO_SERVICE_CREDIT = 'credit'
CIELO_SERVICE_DEBIT = 'debit'

CIELO_CREDIT_CARD_INFO_KEY = 'cielo_credit'
CIELO_DEBIT_CARD_INFO_KEY = 'cielo_debit'
CIELO_TID_INFO_KEY = 'cielo_tid'

INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING = _('{0}x of {1} | Total={2})')
INSTALLMENT_CHOICE_WITH_INTEREST_STRING = _('{0}x of {1} | Total={2} | Interest rate: {3}%)')


class InterestType(object):
    '''
    Tipo de de cálculo de juros
    '''
    Simple = 'S'
    Price = 'P'


class CieloProduct(object):
    '''
    Produtoa Cielo
    Cŕedito, Parcelado loja ou Débito
    '''
    Credit = '1'
    InstallmentCredit = '2'
    Debit = 'A'


class CieloCardBrand(object):
    Visa = 'visa'
    Mastercard = 'mastercard'
    Diners = 'diners'
    Discover = 'discover'
    Elo = 'elo'
    Amex = 'amex'
    Jcb = 'jcb'
    Aura = 'aura'
    Unknown = 'unknown'


class CieloTransactionStatus(Enum):
    NotCreated = -1
    Created = 0
    InProgress = 1
    Authenticated = 2
    NotAuthenticated = 3
    Authorized = 4
    NotAuthorized = 5
    Captured = 6
    Cancelled = 9
    Authenticating = 10
    Cancelling = 12

    class Labels:
        NotCreated = _('Not created')
        Created = _('Created')
        InProgress = _('In progress')
        Authenticated = _('Authenticated')
        NotAuthenticated = _('Not authenticated')
        Authorized = _('Authorized')
        NotAuthorized = _('Not authorized')
        Captured = _('Captured')
        Cancelled = _('Cancelled')
        Authenticating = _('Authenticating')
        Cancelling = _('Cancelling')


CieloErrorMap = {
    1: _('Mensagem inválida'),
    2: _('Credenciais inválidas'),
    3: _('Transação inexistente'),
    8: _('Código de Segurança Inválido'),
    10: _('Inconsistência no envio do cartão'),
    11: _('Modalidade não habilitada'),
    12: _('Número de parcelas inválido'),
    13: _('Flag de autorização automática'),
    14: _('Autorização Direta inválida'),
    15: _('Autorização Direta sem Cartão'),
    16: _('Identificador, TID, inválido'),
    17: _('Código de segurança ausente'),
    18: _('Indicador de código de segurança inconsistente'),
    19: _('URL de Retorno não fornecida'),
    20: _('Status não permite autorização'),
    21: _('Prazo de autorização vencido'),
    22: _('Número de parcelas inválido'),
    25: _('Encaminhamento a autorização não permitido'),
    30: _('Status inválido para captura'),
    31: _('Prazo de captura vencido'),
    32: _('Valor de captura inválido'),
    33: _('Falha ao capturar'),
    34: _('Valor da taxa de embarque obrigatório'),
    35: _('Bandeira inválida para utilização da Taxa de Embarque'),
    36: _('Produto inválido para utilização da Taxa de Embarque'),
    40: _('Prazo de cancelamento vencido'),
    42: _('Falha ao cancelar'),
    43: _('Valor de cancelamento é maior que valor autorizado.'),
    51: _('Recorrência Inválida'),
    52: _('Token Inválido'),
    53: _('Recorrência não habilitada'),
    54: _('Transação com Token inválida'),
    55: _('Número do cartão não fornecido'),
    56: _('Validade do cartão não fornecido'),
    57: _('Erro inesperado gerando Token'),
    61: _('Transação Recorrente Inválida'),
    77: _('XID não fornecido'),
    78: _('CAVV não fornecido'),
    86: _('XID e CAVV não fornecidos'),
    87: _('CAVV com tamanho divergente'),
    88: _('XID com tamanho divergente'),
    89: _('ECI com tamanho divergente'),
    90: _('ECI inválido'),
    95: _('Erro interno de autenticação'),
    97: _('Sistema indisponível'),
    98: _('Timeout'),
    99: _('Erro inesperado'),
}


CieloAuthorizationCode = {
    '00': {'msg': _('Autorizado.'), 'internal_msg': _('Transação autorizada'), 'retry': False},
    '01': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Transação referida pelo banco emissor'), 'retry': False},
    '04': {'msg': _('Tente novamente.'), 'internal_msg': _('Transação não autorizada'), 'retry': True},
    '05': {'msg': _('Tente novamente.'), 'internal_msg': _('Transação não autorizada'), 'retry': True},
    '06': {'msg': _('Tente novamente.'), 'internal_msg': _('Tente novamente'), 'retry': True},
    '07': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Cartão com restrição'), 'retry': False},
    '08': {'msg': _('Código de segurança inválido.'), 'internal_msg': _('Código de segurança inválido'), 'retry': False},
    '11': {'msg': _('Autorizado.'), 'internal_msg': _('Transação autorizada'), 'retry': False},
    '13': {'msg': _('Valor inválido.'), 'internal_msg': _('Valor inválido'), 'retry': False},
    '14': {'msg': _('Cartão inválido. Informe corretamente os dados e tente novamente.'), 'internal_msg': _('Cartão inválido'), 'retry': False},
    '15': {'msg': _('Aguarde alguns instantes e tente novamente.'), 'internal_msg': _('Banco emissor indisponível'), 'retry': True},
    '21': {'msg': _('Problema interno. Contate o atendimento da loja.'), 'internal_msg': _('Cancelamento não efetuado'), 'retry': False},
    '41': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Cartão com restrição'), 'retry': False},
    '51': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Saldo insuficiente'), 'retry': True},
    '54': {'msg': _('Cartão vencido.'), 'internal_msg': _('Cartão vencido'), 'retry': False},
    '57': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Transação não permitida'), 'retry': True},
    '60': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Transação não autorizada'), 'retry': False},
    '62': {'msg': _('Contate o emissor do seu cartão.'), 'internal_msg': _('Transação não autorizada'), 'retry': False},
    '78': {'msg': _('Cartão bloqueado.'), 'internal_msg': _('Cartão não foi desbloqueado pelo portador'), 'retry': True},
    '82': {'msg': _('Cartão inválido.'), 'internal_msg': _('Erro no cartão'), 'retry': True},
    '91': {'msg': _('Aguarde alguns instantes e tente novamente.'), 'internal_msg': _('Banco fora do ar'), 'retry': True},
    '96': {'msg': _('Aguarde alguns instantes e tente novamente.'), 'internal_msg': _('Tente novamente'), 'retry': True},
    'AA': {'msg': _('Aguarde alguns instantes e tente novamente.'), 'internal_msg': _('Tempo excedido'), 'retry': True},
    'AC': {'msg': _('Cartão somente aceita a função Débito. Altere a forma de pagamento.'), 'internal_msg': _('Use função débito'), 'retry': False},
    'GA': {'msg': _('Aguarde alguns instantes e tente novamente.'), 'internal_msg': _('Transação referida pela Cielo'), 'retry': True},
}


CIELO_UKNOWN_ERROR_MSG = _('Unknown error')


CIELO_AUTHORIZED_STATUSES = ("00", "11")


class CieloAuthorizationType(object):
    OnlyAuthenticate = 0
    OnyIfAuthenticated = 1
    IfAuthenticatedOrNot = 2
    Direct = 3
    Recurrent = 4


# Matrix dos produtos Cielo contendo o que cada bandeira aceita
CieloProductMatrix = {
    CieloCardBrand.Visa: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: True,
        "cvv_length": 3
    },
    CieloCardBrand.Mastercard: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: True,
        "cvv_length": 3
    },
    CieloCardBrand.Amex: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: False,
        "cvv_length": 4
    },
    CieloCardBrand.Elo: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: False,
        "cvv_length": 3
    },
    CieloCardBrand.Diners: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: False,
        "cvv_length": 3
    },
    CieloCardBrand.Discover: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: False,
        CieloProduct.Debit: False,
        "cvv_length": 3
    },
    CieloCardBrand.Jcb: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: False,
        "cvv_length": 3
    },
    CieloCardBrand.Aura: {
        CieloProduct.Credit: True,
        CieloProduct.InstallmentCredit: True,
        CieloProduct.Debit: False,
        "cvv_length": 3
    }
}


CIELO_CREDITCARD_BRAND_CHOICES = (
    (CieloCardBrand.Visa, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/visa.png')))),
    (CieloCardBrand.Mastercard, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/mastercard.png')))),
    (CieloCardBrand.Elo, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/elo.png')))),
    (CieloCardBrand.Amex, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/amex.png')))),
    (CieloCardBrand.Diners, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/diners.png')))),
    (CieloCardBrand.Aura, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/aura.png')))),
    (CieloCardBrand.Discover, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/discover.png')))),
    (CieloCardBrand.Jcb, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/jcb.png')))),
)


CIELO_DEBITCARD_BRAND_CHOICES = (
    (CieloCardBrand.Visa, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/visa_electron.png')))),
    (CieloCardBrand.Mastercard, mark_safe('<img width="50" height="50" src="{0}">'.format(static('img/maestro.png')))),
)


CIELO_PRODUCT_CHOICES = (
    (CieloProduct.Credit, _('Credit')),
    (CieloProduct.InstallmentCredit, _('Installment credit')),
    (CieloProduct.Debit, _('Debit')),
)


INTEREST_TYPE_CHOICES = (
    (InterestType.Simple, _('Simple')),
    (InterestType.Price, _('PRICE table')),
)


CIELO_AUTHORIZATION_TYPE_CHOICES = (
    (CieloAuthorizationType.OnlyAuthenticate, _('Only authenticate')),
    (CieloAuthorizationType.OnyIfAuthenticated, _('Only if the transaction gets authenticated')),
    (CieloAuthorizationType.IfAuthenticatedOrNot, _('If the transaction gets authenticated or not')),
    (CieloAuthorizationType.Direct, _('Direct, do not authenticate')),
    (CieloAuthorizationType.Recurrent, _('Recurrent')),
)
