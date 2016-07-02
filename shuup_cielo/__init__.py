# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.


__version__ = "1.0.0"

default_app_config = "shuup_cielo.apps.ShuupCieloAppConfig"

'''
    TODO:
    * Poder visualizar as transações que não possuem pedidos relacionados
    * Criar model para registrar datas e valores de capturas e estornos
    * REST para obter parcelamento por bandeira
    * Quando o Shuup possibilitar a retentativa de pagamento
      não cancelar o pedido se der erro na transação e sim
      informar o usuário par atentar novamente ou redirecionar
      para uma página especial da Cielo para retentar
    * Ver uma melhor maneira de armazenar temporariamente os dados do cartao
    * Obter dados adicionais do portador do Cartão como CPF e Data de nascimento
'''
