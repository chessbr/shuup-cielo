# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

from django.core.urlresolvers import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from django.views.generic.edit import DeleteView

from shuup.admin.utils.picotable import Column, TextFilter
from shuup.admin.utils.views import CreateOrUpdateView, PicotableListView
from shuup_cielo.admin.forms import CieloConfigForm
from shuup_cielo.models import CieloConfig


class ConfigListView(PicotableListView):
    model = CieloConfig
    columns = [
        Column("shop", _("Shop"), filter_config=TextFilter()),
        Column("ec_num", _("Affiliation number"), filter_config=TextFilter()),
    ]


class ConfigEditView(CreateOrUpdateView):
    model = CieloConfig
    form_class = CieloConfigForm
    template_name = "cielo/admin/config_edit.jinja"
    context_object_name = "config"


class ConfigDeleteView(DeleteView):
    model = CieloConfig
    success_url = reverse_lazy("shuup_admin:cielo.config.list")
