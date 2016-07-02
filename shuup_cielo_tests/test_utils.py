# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from decimal import Decimal

from shuup_cielo.utils import decimal_to_int_cents, InstallmentCalculator, is_cc_valid, safe_int


def test_validate_cc_number():
    assert is_cc_valid('') is False
    assert is_cc_valid('3241432103521') is False
    assert is_cc_valid(None) is False
    assert is_cc_valid('4916098011122629') is False

    # Visa
    assert is_cc_valid('4916098011122628') is True
    assert is_cc_valid(4916098011122628) is True
    assert is_cc_valid('4532822834712628') is True
    assert is_cc_valid('4024007111447875') is True
    assert is_cc_valid('4024007109186873') is True
    assert is_cc_valid('4929539983359909') is True

    # Master
    assert is_cc_valid(5186874207232219) is True
    assert is_cc_valid('5186874207232219') is True
    assert is_cc_valid('5586546636847264') is True
    assert is_cc_valid('5561076667456669') is True
    assert is_cc_valid('5299834823788014') is True
    assert is_cc_valid('5117513126931766') is True

    # Discover
    assert is_cc_valid(6011901831046431) is True
    assert is_cc_valid('6011901831046431') is True
    assert is_cc_valid('6011772223381433') is True
    assert is_cc_valid('6011749929058911') is True
    assert is_cc_valid('6011020329229837') is True
    assert is_cc_valid('6011552504005582') is True

    # Amex
    assert is_cc_valid(378111329315310) is True
    assert is_cc_valid('378111329315310') is True
    assert is_cc_valid('373084727757687') is True
    assert is_cc_valid('371508228528470') is True
    assert is_cc_valid('342485720394451') is True
    assert is_cc_valid('349696561160339') is True
    
def test_safe_inf():
    assert safe_int('') == 0
    assert safe_int(None) == 0
    assert safe_int(-1) == -1
    assert safe_int(123.321312) == 123
    assert safe_int(1) == 1

def test_decimal_to_int_cents():
    assert decimal_to_int_cents(32131) == 3213100
    assert decimal_to_int_cents(13.321) == 1332
    assert decimal_to_int_cents('32.41312312') == 3241
    assert decimal_to_int_cents('0.0001') == 0
    assert decimal_to_int_cents('0.01') == 1

def test_price_interest():
    # Valor financiado=74085.12  parcelas=27  juros=7.54%
    total, installment = InstallmentCalculator.price_interest(Decimal(74085.12), 27, Decimal(7.54))
    assert abs(installment - Decimal(6498.98)) < 0.01
    assert abs(total - Decimal(175472.57)) < 0.01
    
    # Valor financiado=1000  parcelas=10  juros=1.99%
    total, installment = InstallmentCalculator.price_interest(Decimal(1000), 10, Decimal(1.99))
    assert abs(installment - Decimal(111.27)) < 0.01
    assert abs(total - Decimal(1112.68)) < 0.01

def test_simple_interest():
    # Valor financiado=74085.12  parcelas=27  juros=7.54%
    total, installment = InstallmentCalculator.simple_interest(Decimal(74085.12), 27, Decimal(7.54))
    assert abs(installment - Decimal(8329.91)) < 0.01
    assert abs(total - Decimal(224907.60)) < 0.01
    
    # Valor financiado=1000  parcelas=10  juros=1.99%
    total, installment = InstallmentCalculator.simple_interest(Decimal(1000), 10, Decimal(1.99))
    assert abs(installment - Decimal(119.9)) < 0.01
    assert abs(total - Decimal(1199)) < 0.01
