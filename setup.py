# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

import setuptools

"""
TIP:
    To extract messages:
        python -m shuup_workbench shuup_makemessages --no-pot-date --no-wrap --include-location -l pt_BR

    To compile messages:
        python -m shuup_workbench compilemessages
"""

NAME = 'shuup-cielo'
VERSION = '1.0.0'
DESCRIPTION = 'Cielo gateway payment add-on for Shuup'
AUTHOR = 'Rockho Team'
AUTHOR_EMAIL = 'rockho@rockho.com.br'
URL = 'http://www.rockho.com.br/'
LICENSE = 'AGPL-3.0'

EXCLUDED_PACKAGES = [
    'shuup_cielo_tests', 'shuup_cielo_tests.*',
]

REQUIRES = [
    "python-cielo-webservice",
    "iso8601"
]

if __name__ == '__main__':
    setuptools.setup(
        name=NAME,
        version=VERSION,
        description=DESCRIPTION,
        url=URL,
        author=AUTHOR,
        author_email=AUTHOR_EMAIL,
        license=LICENSE,
        packages=["shuup_cielo"],
        include_package_data=True,
        install_requires=REQUIRES,
        entry_points={"shuup.addon": "shuup_cielo=shuup_cielo"}
    )
