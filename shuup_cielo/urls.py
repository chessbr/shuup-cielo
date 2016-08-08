# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from shuup_cielo.views import AuthRedirectView

from django.conf.urls import patterns, url

urlpatterns = patterns(
    '',
    url(r'^checkout/auth-redirect/$', AuthRedirectView.as_view(), name='checkout_auth_redirect'),
)
