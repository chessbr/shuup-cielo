# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import division, unicode_literals

from decimal import Decimal
import math


def is_cc_valid(cc_number):
    '''
    From http://andreinc.net/2011/04/09/credit-card-validation/
    '''

    # make the number a long integer
    try:
        cc_number = int(cc_number)
    except:
        return False

    digits = [int(x) for x in reversed(str(cc_number))]
    check_sum = sum(digits[::2]) + sum(((dig // 10) + (dig % 10)) for dig in [2 * el for el in digits[1::2]])
    return (check_sum % 10) == 0


def safe_int(num):
    '''
    Parses and return safely an int
    '''

    try:
        return int(num)
    except:
        return 0


def decimal_to_int_cents(amount):
    '''
    Convert decimal (13.24) into cents (1324)
    '''
    return safe_int(Decimal(amount) * 100)


class InstallmentCalculator(object):

    @staticmethod
    def price_interest(amount, installments, interest_rate):
        '''
        Calculates an installment with PRICE table method

        :type: amount: Decimal
        :type: installments: int
        :type: interest_rate: Decimal

        :rtype: (Decimal, Decimal)
        :return: (total with interest, installment amount)
        '''

        one = Decimal(1.0)
        interest_rate = interest_rate / Decimal(100)
        coefficient = interest_rate / (one - (one / Decimal(math.pow(one + interest_rate, installments))))
        installment_amount = (coefficient * amount)

        return (installment_amount * installments, installment_amount)

    @staticmethod
    def simple_interest(amount, installments, interest_rate):
        '''
        Calculates an installment with simple interest method

        :type: amount: Decimal
        :type: installments: int
        :type: interest_rate: Decimal

        :rtype: (Decimal, Decimal)
        :return: (total with interest, installment amount)
        '''

        interest_rate = interest_rate / Decimal(100)
        total = amount + Decimal(amount * installments * interest_rate)

        return (total, total / installments)
