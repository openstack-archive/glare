# Copyright 2010 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import memcache
from oslo_config import cfg
from oslo_log import log as logging
import pprint
import requests
import webob.dec

from glare.common import exception

LOG = logging.getLogger(__name__)

keycloak_oidc_opts = [
    cfg.StrOpt(
        'auth_url',
        help='Keycloak base url (e.g. https://my.keycloak:8443/auth)'
    ),
    cfg.StrOpt(
        'insecure',
        default=False,
        help='If True, SSL/TLS certificate verification is disabled'
    ),
    cfg.StrOpt(
        'memcached_server',
        default=None,
        help='Url of memcached server to use for caching'
    ),
    cfg.IntOpt(
        'token_cache_time',
        default=60,
        min=0,
        help='In order to prevent excessive effort spent validating '
             'tokens, the middleware caches previously-seen tokens '
             'for a configurable duration (in seconds).'
    ),
]

CONF = cfg.CONF
CONF.register_opts(keycloak_oidc_opts, group="keycloak_oidc")


class KeycloakAuthMiddleware(object):
    def __init__(self, app):
        self.app = app
        mcserv_url = CONF.memcached_server
        self.mcclient = memcache.Client(mcserv_url) if mcserv_url else None

    def authenticate(self, request):
        realm_name = request.headers.get('X-Project-Id')

        user_info_endpoint = (
            "%s/realms/%s/protocol/openid-connect/userinfo" %
            (CONF.keycloak_oidc.auth_url, realm_name)
        )

        access_token = request.headers.get('X-Auth-Token')

        info = None
        if self.mcclient:
            info = self.mcclient.get(access_token)

        if info is None:
            resp = requests.get(
                user_info_endpoint,
                headers={"Authorization": "Bearer %s" % access_token},
                verify=not CONF.keycloak_oidc.insecure
            )
            resp.raise_for_status()
            if self.mcclient:
                self.mcclient.set(access_token, resp.json(),
                                  time=CONF.token_cache_time)
            info = resp.json()

        LOG.debug(
            "HTTP response from OIDC provider: %s" %
            pprint.pformat(info)
        )

        return info

    def get_roles(self, request):
        realm_name = request.headers.get('X-Project-Id')

        user_roles_endpoint = (
            "%s/realms/%s/roles" %
            (CONF.keycloak_oidc.auth_url, realm_name)
        )

        access_token = request.headers.get('X-Auth-Token')

        roles = None
        if self.mcclient:
            roles = self.mcclient.get(realm_name)

        if roles is None:
            resp = requests.get(
                user_roles_endpoint,
                headers={"Authorization": "Bearer %s" % access_token}
            )
            roles = [role['name'] for role in resp.json()]
            if self.mcclient:
                self.mcclient.set(realm_name, roles,
                                  time=CONF.token_cache_time)

        LOG.debug(
            "Roles for realm %s: %s" %
            (realm_name, pprint.pformat(roles))
        )

        return roles

    @webob.dec.wsgify
    def __call__(self, request):
        if 'X-Project-Id' not in request.headers:
            raise exception.Unauthorized()
        self.authenticate(request)
        roles = ','.join(self.get_roles(request))
        request.headers["X-Identity-Status"] = "Confirmed"
        request.headers["X-Roles"] = roles
        return request.get_response(self.app)
