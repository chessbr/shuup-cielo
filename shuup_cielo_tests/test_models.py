# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from decimal import Decimal

import pytest

from shuup_cielo.models import DiscountPercentageBehaviorComponent
from shuup_tests.core.test_order_creator import seed_source

from shuup.core.models._order_lines import OrderLineType
from shuup.testing.factories import (
    create_product, get_default_payment_method, get_default_shipping_method, get_default_supplier
)


# Testar InstallmentContext

@pytest.mark.django_db
@pytest.mark.parametrize("get_service,service_attr", [
    (get_default_payment_method, "payment_method"),
    (get_default_shipping_method, "shipping_method")
])
def test_discount_service_behavior(admin_user, get_service, service_attr):
    DISCOUNT_PERC = Decimal(8.0)
    PRODUCT_PRICE = Decimal(2.5)
    PRODUCT_QTNTY = 4

    service = get_service()
    component = DiscountPercentageBehaviorComponent.objects.create(percentage=DISCOUNT_PERC)
    service.behavior_components.add(component)

    source = seed_source(admin_user)
    supplier = get_default_supplier()
    product = create_product(
        sku="39917329183",
        shop=source.shop,
        supplier=supplier,
        default_price=PRODUCT_PRICE
    )
    source.add_line(
        type=OrderLineType.PRODUCT,
        product=product,
        supplier=supplier,
        quantity=PRODUCT_QTNTY,
        base_unit_price=source.create_price(PRODUCT_PRICE),
    )

    setattr(source, service_attr, service)
    assert getattr(source, service_attr) == service
    assert service.behavior_components.count() == 1

    costs = list(service.get_costs(source))
    unavailability_reasons = list(service.get_unavailability_reasons(source))
    assert not unavailability_reasons and costs

    assert len(costs) == 1
    assert costs[0].price.value == (PRODUCT_QTNTY * PRODUCT_PRICE) * (-DISCOUNT_PERC) / Decimal(100.0)
