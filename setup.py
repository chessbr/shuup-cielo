# -*- coding: utf-8 -*-
# This file is part of Shuup Cielo.
#
# Copyright (c) 2016, Rockho Team. All rights reserved.
# Author: Christian Hess
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.

from babel.messages import frontend as babel
import setuptools

"""
    How to translate:
    Babel integration: http://babel.pocoo.org/en/stable/setup.html

    - Extract messages:
        `python setup.py extract_messages -D django --output-file shuup_cielo/locale/django.pot`

    - Update an existing catalog (language):
        `python setup.py -D django update_catalog -l pt_BR -i shuup_cielo/locale/django.pot -d shuup_cielo/locale`

    - Compile catalog:
        `python setup.py compile_catalog -D django -d shuup_cielo/locale -l pt_BR`

    - Create a new catalog (language):
        `python setup.py init_catalog -D django -l pt_BR -i shuup_cielo/locale/django.pot -d shuup_cielo/locale`
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
        entry_points={"shuup.addon": "shuup_cielo=shuup_cielo"},
        cmdclass={'compile_catalog': babel.compile_catalog,
                  'extract_messages': babel.extract_messages,
                  'init_catalog': babel.init_catalog,
                  'update_catalog': babel.update_catalog},
        message_extractors={
            'shuup_cielo': [
                ('**.py', 'python', None),
                ('**/templates/**.html', 'jinja2', None),
                ('**/templates/**.jinja', 'jinja2', None)
            ],
        }
    )
