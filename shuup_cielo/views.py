# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

import base64

from django.views.generic.base import TemplateView


class AuthRedirectView(TemplateView):
    template_name = "cielo/auth_redirect.jinja"

    def get_context_data(self, **kwargs):
        context = super(AuthRedirectView, self).get_context_data(**kwargs)
        context['redirect_url'] = base64.b64decode(self.request.GET.get('auth_url', '').encode()).decode()
        return context
