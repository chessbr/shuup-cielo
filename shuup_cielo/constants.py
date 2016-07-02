# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from enumfields import Enum

from django.utils.translation import ugettext_lazy as _

CIELO_SERVICE_CREDIT = 'credit'
CIELO_SERVICE_DEBIT = 'debit'

CIELO_CREDIT_CARD_INFO_KEY = 'cielows15_credit'
CIELO_DEBIT_CARD_INFO_KEY = 'cielows15_debit'
CIELO_INSTALLMENT_INFO_KEY = 'cielows15_installment'
CIELO_TID_INFO_KEY = 'cielows15_tid'


INSTALLMENT_CHOICE_WITHOUT_INTEREST_STRING = _(u'{0}x of {1} | Total={2})')
INSTALLMENT_CHOICE_WITH_INTEREST_STRING = _(u'{0}x of {1} | Total={2} | Interest rate: {3}%)')


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
        Created = _(u'Created')
        InProgress = _(u'In progress')
        Authenticated = _(u'Authenticated')
        NotAuthenticated = _(u'Not authenticated')
        Authorized = _(u'Authorized')
        NotAuthorized = _(u'Not authorized')
        Captured = _(u'Captured')
        Cancelled = _(u'Cancelled')
        Authenticating = _(u'Authenticating')
        Cancelling = _(u'Cancelling')


CieloErrorMap = {
    1: _(u'Mensagem inválida'),
    2: _(u'Credenciais inválidas'),
    3: _(u'Transação inexistente'),
    8: _(u'Código de Segurança Inválido'),
    10: _(u'Inconsistência no envio do cartão'),
    11: _(u'Modalidade não habilitada'),
    12: _(u'Número de parcelas inválido'),
    13: _(u'Flag de autorização automática'),
    14: _(u'Autorização Direta inválida'),
    15: _(u'Autorização Direta sem Cartão'),
    16: _(u'Identificador, TID, inválido'),
    17: _(u'Código de segurança ausente'),
    18: _(u'Indicador de código de segurança inconsistente'),
    19: _(u'URL de Retorno não fornecida'),
    20: _(u'Status não permite autorização'),
    21: _(u'Prazo de autorização vencido'),
    22: _(u'Número de parcelas inválido'),
    25: _(u'Encaminhamento a autorização não permitido'),
    30: _(u'Status inválido para captura'),
    31: _(u'Prazo de captura vencido'),
    32: _(u'Valor de captura inválido'),
    33: _(u'Falha ao capturar'),
    34: _(u'Valor da taxa de embarque obrigatório'),
    35: _(u'Bandeira inválida para utilização da Taxa de Embarque'),
    36: _(u'Produto inválido para utilização da Taxa de Embarque'),
    40: _(u'Prazo de cancelamento vencido'),
    42: _(u'Falha ao cancelar'),
    43: _(u'Valor de cancelamento é maior que valor autorizado.'),
    51: _(u'Recorrência Inválida'),
    52: _(u'Token Inválido'),
    53: _(u'Recorrência não habilitada'),
    54: _(u'Transação com Token inválida'),
    55: _(u'Número do cartão não fornecido'),
    56: _(u'Validade do cartão não fornecido'),
    57: _(u'Erro inesperado gerando Token'),
    61: _(u'Transação Recorrente Inválida'),
    77: _(u'XID não fornecido'),
    78: _(u'CAVV não fornecido'),
    86: _(u'XID e CAVV não fornecidos'),
    87: _(u'CAVV com tamanho divergente'),
    88: _(u'XID com tamanho divergente'),
    89: _(u'ECI com tamanho divergente'),
    90: _(u'ECI inválido'),
    95: _(u'Erro interno de autenticação'),
    97: _(u'Sistema indisponível'),
    98: _(u'Timeout'),
    99: _(u'Erro inesperado'),
}


CieloAuthorizationCode = {
    '0': {'msg': _(u'Transação autorizada'), 'retry': False},
    '1': {'msg': _(u'Transação referida pelo banco emissor'), 'retry': False},
    '4': {'msg': _(u'Transação False autorizada'), 'retry': True},
    '5': {'msg': _(u'Transação False autorizada'), 'retry': True},
    '6': {'msg': _(u'Tente novamente'), 'retry': True},
    '7': {'msg': _(u'Cartão com restrição'), 'retry': False},
    '8': {'msg': _(u'Código de segurança inválido'), 'retry': False},
    '11': {'msg': _(u'Transação autorizada'), 'retry': False},
    '13': {'msg': _(u'Valor inválido'), 'retry': False},
    '14': {'msg': _(u'Cartão inválido'), 'retry': False},
    '15': {'msg': _(u'Banco emissor indisponível'), 'retry': True},
    '21': {'msg': _(u'Cancelamento False efetuado'), 'retry': False},
    '41': {'msg': _(u'Cartão com restrição'), 'retry': False},
    '51': {'msg': _(u'Saldo insuficiente'), 'retry': True},
    '54': {'msg': _(u'Cartão vencido'), 'retry': False},
    '57': {'msg': _(u'Transação False permitida'), 'retry': True},
    '60': {'msg': _(u'Transação False autorizada'), 'retry': False},
    '62': {'msg': _(u'Transação False autorizada'), 'retry': False},
    '78': {'msg': _(u'Cartão False foi desbloqueado pelo portador'), 'retry': True},
    '82': {'msg': _(u'Erro no cartão'), 'retry': True},
    '91': {'msg': _(u'Banco fora do ar'), 'retry': True},
    '96': {'msg': _(u'Tente novamente'), 'retry': True},
    'AA': {'msg': _(u'Tempo excedido'), 'retry': True},
    'AC': {'msg': _(u'Use função débito'), 'retry': False},
    'GA': {'msg': _(u'Transação referida pela Cielo'), 'retry': True},
}


class CieloAuthorizationType(object):
    OnlyAuthenticate = 0
    OnyIfAuthenticated = 1
    IfAuthenticatedOrNot = 2
    Direct = 3
    Recurrent = 4


# Matrix dos produtos Cielo contendo o que cada bandeira aceita
CieloProductMatrix = {
    CieloCardBrand.Visa:        {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: True},
    CieloCardBrand.Mastercard:  {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: True},
    CieloCardBrand.Amex:        {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: False},
    CieloCardBrand.Elo:         {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: False},
    CieloCardBrand.Diners:      {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: False},
    CieloCardBrand.Discover:    {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: False,  CieloProduct.Debit: False},
    CieloCardBrand.Jcb:         {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: False},
    CieloCardBrand.Aura:        {CieloProduct.Credit: True,    CieloProduct.InstallmentCredit: True,   CieloProduct.Debit: False},
}


CIELO_CARD_BRAND_CHOICES = (
    (CieloCardBrand.Amex, 'American Express'),
    (CieloCardBrand.Aura, 'Aura'),
    (CieloCardBrand.Discover, 'Discover'),
    (CieloCardBrand.Visa, 'Visa'),
    (CieloCardBrand.Mastercard, 'Mastercard'),
    (CieloCardBrand.Jcb, 'JCB'),
    (CieloCardBrand.Diners, 'Diners'),
    (CieloCardBrand.Elo, 'Elo'),
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
    (CieloAuthorizationType.OnlyAuthenticate, _(u'Only authenticate')),
    (CieloAuthorizationType.OnyIfAuthenticated, _(u'Only if the transaction gets authenticated')),
    (CieloAuthorizationType.IfAuthenticatedOrNot, _(u'If the transaction gets authenticated or not')),
    (CieloAuthorizationType.Direct, _(u'Direct, do not authenticate')),
    (CieloAuthorizationType.Recurrent, _(u'Recurrent')),
)
