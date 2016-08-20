# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from shuup_cielo.views import GetInstallmentsOptionsView, TransactionReturnView, TransactionView

from django.conf.urls import patterns, url
from django.views.decorators.csrf import csrf_exempt

urlpatterns = patterns(
    '',
    url(r'^checkout/installment/$', GetInstallmentsOptionsView.as_view(),
        name='cielo_get_installment_options'),

    url(r'^checkout/transaction/$', TransactionView.as_view(),
        name='cielo_make_transaction'),

    url(r'^checkout/return/(?P<cielo_order_pk>\d+)/$',
        csrf_exempt(TransactionReturnView.as_view()),
        name='cielo_transaction_return')
)
