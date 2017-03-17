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

import jwt
import memcache
from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import base as base_middleware
import pprint
import requests
import webob.dec

from glare.common import exception
from glare.i18n import _

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


class KeycloakAuthMiddleware(base_middleware.Middleware):
    def __init__(self, app):
        super(KeycloakAuthMiddleware, self).__init__(application=app)
        mcserv_url = CONF.keycloak_oidc.memcached_server
        self.mcclient = memcache.Client(mcserv_url) if mcserv_url else None

    def authenticate(self, access_token, realm_name):
        user_info_endpoint = (
            "%s/realms/%s/protocol/openid-connect/userinfo" %
            (CONF.keycloak_oidc.auth_url, realm_name)
        )

        info = None
        if self.mcclient:
            info = self.mcclient.get(access_token)

        if info is None:
            resp = requests.get(
                user_info_endpoint,
                headers={"Authorization": "Bearer %s" % access_token},
                verify=not CONF.keycloak_oidc.insecure
            )
            if resp.status_code == 401:
                raise exception.Unauthorized(message=resp.text)
            elif resp.status_code >= 400:
                raise exception.GlareException(message=resp.text)

            if self.mcclient:
                self.mcclient.set(access_token, resp.json(),
                                  time=CONF.keycloak_oidc.token_cache_time)
            info = resp.json()

        LOG.debug(
            "HTTP response from OIDC provider: %s" %
            pprint.pformat(info)
        )

        return info

    @webob.dec.wsgify
    def __call__(self, request):
        if 'X-Auth-Token' not in request.headers:
            msg = _("Auth token must be provided in 'X-Auth-Token' header.")
            LOG.error(msg)
            raise exception.Unauthorized()
        access_token = request.headers.get('X-Auth-Token')
        try:
            decoded = jwt.decode(access_token, algorithms=['RS256'],
                                 verify=False)
        except Exception:
            msg = _("Token can't be decoded because of wrong format.")
            LOG.error(msg)
            raise exception.Unauthorized()

        # Get user realm from parsed token
        # Format is "iss": "http://<host>:<port>/auth/realms/<realm_name>",
        __, __, realm_name = decoded['iss'].strip().rpartition('/realms/')

        # Get roles from from parsed token
        roles = ','.join(decoded['realm_access']['roles']) \
            if 'realm_access' in decoded else ''

        self.authenticate(access_token, realm_name)

        request.headers["X-Identity-Status"] = "Confirmed"
        request.headers["X-Project-Id"] = realm_name
        request.headers["X-Roles"] = roles
        return request.get_response(self.application)
