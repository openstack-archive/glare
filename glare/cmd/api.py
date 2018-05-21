#!/usr/bin/env python
#
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


"""
Glare (Glare Artifact Repository) API service.
"""

import sys

import eventlet
from oslo_utils import encodeutils

eventlet.patcher.monkey_patch(all=False, socket=True, time=True,
                              select=True, thread=True, os=True, MySQLdb=True)

import os

# If ../glare/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glare', '__init__.py')):
    sys.path.insert(0, possible_topdir)

import glance_store
from oslo_config import cfg
from oslo_log import log as logging
from osprofiler import initializer

from glare.common import config
from glare.common import exception
from glare.common import wsgi
from glare import notification


CONF = cfg.CONF
CONF.import_group("profiler", "glare.common.wsgi")
logging.register_options(CONF)

KNOWN_EXCEPTIONS = (RuntimeError,
                    exception.WorkerCreationFailure,
                    glance_store.exceptions.BadStoreConfiguration)


def fail(e):
    global KNOWN_EXCEPTIONS
    return_code = KNOWN_EXCEPTIONS.index(type(e)) + 1
    sys.stderr.write("ERROR: %s\n" % encodeutils.exception_to_unicode(e))
    sys.exit(return_code)


def main():
    try:
        config.parse_args()
        wsgi.set_eventlet_hub()
        logging.setup(CONF, 'glare')
        notification.set_defaults()

        if CONF.profiler.enabled:
            initializer.init_from_conf(
                conf=CONF,
                context={},
                project="glare",
                service="api",
                host=CONF.bind_host
            )

        server = wsgi.Server(initialize_glance_store=True)
        server.start(config.load_paste_app('glare-api'), default_port=9494)
        server.wait()
    except KNOWN_EXCEPTIONS as e:
        fail(e)


if __name__ == '__main__':
    main()
