# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Glare WSGI module.

Use this module to deploy glare as WSGI application.

Sample usage with uwsgi:

    export GLARE_CONFIG_FILE=/etc/glare/glare.conf
    uwsgi --module glare.wsgi:application --socket 127.0.0.1:8008

Sample apache mod_wsgi configuration:

    <VirtualHost *:80>
         ServerName example.com
         SetEnv GLARE_CONFIG_FILE=/etc/glare/glare.conf
         DocumentRoot /path/to/public_html/
         WSGIScriptAlias / /usr/lib/python2.7/site-packages/glare/wsgi.py
         ...
    </VirtualHost>

"""

import os

from oslo_config import cfg
from oslo_log import log as logging

from glare.common import config
from glare.common import utils


CONF = cfg.CONF
logging.register_options(CONF)
CONFIG_FILE = os.environ.get("GLARE_CONFIG_FILE", "etc/glare.conf")
config.parse_args(args=["--config-file", CONFIG_FILE])

utils.initialize_glance_store()

application = config.load_paste_app('glare-api')
