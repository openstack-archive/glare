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
import glare.api.middleware.keycloak_auth
import glare.api.v1.resource
import glare.api.versions
import glare.common.config
import glare.common.wsgi
import glare.notification
import glare.objects.base
from glare.objects.meta import registry
import glare.scrubber

_artifacts_opts = [
    (None, list(itertools.chain(
        glare.api.middleware.context.context_opts,
        glare.api.v1.resource.list_configs,
        glare.api.versions.versions_opts,
        glare.common.config.common_opts,
        glare.common.wsgi.bind_opts,
        glare.common.wsgi.eventlet_opts,
        glare.common.wsgi.socket_opts,
        glare.notification.notifier_opts,
        glare.objects.base.global_artifact_opts,
        registry.registry_options))),
    profiler.list_opts()[0],
    ('paste_deploy', glare.common.config.paste_deploy_opts),
    ('keycloak_oidc', glare.api.middleware.keycloak_auth.keycloak_oidc_opts),
    ('scrubber',
     glare.scrubber.scrubber_opts +
     glare.scrubber.scrubber_cmd_opts +
     glare.scrubber.scrubber_cmd_cli_opts)
]

registry.ArtifactRegistry.register_all_artifacts()
for af_type in registry.ArtifactRegistry.obj_classes().values():
    _artifacts_opts.append(
        ('artifact_type:' + af_type[0].get_type_name(),
         af_type[0].list_artifact_type_opts()))


def list_artifacts_opts():
    """Return a list of oslo_config options available in Glare"""
    return [(g, copy.deepcopy(o)) for g, o in _artifacts_opts]
