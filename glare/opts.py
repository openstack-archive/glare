# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

__all__ = [
    'list_artifacts_opts'
]

import copy
import itertools

from osprofiler import opts as profiler

import glare.api.middleware.context
import glare.api.versions
import glare.common.config
import glare.common.wsgi

_artifacts_opts = [
    (None, list(itertools.chain(
        glare.api.middleware.context.context_opts,
        glare.api.versions.versions_opts,
        glare.common.wsgi.bind_opts,
        glare.common.wsgi.eventlet_opts,
        glare.common.wsgi.socket_opts))),
    profiler.list_opts()[0],
    ('paste_deploy', glare.common.config.paste_deploy_opts)
]


def list_artifacts_opts():
    """Return a list of oslo_config options available in Glare"""
    return [(g, copy.deepcopy(o)) for g, o in _artifacts_opts]
