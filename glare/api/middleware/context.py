# Copyright 2011-2016 OpenStack Foundation
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

from oslo_config import cfg
from oslo_context import context
from oslo_log import log as logging
from oslo_middleware import base as base_middleware
from oslo_middleware import request_id
from oslo_serialization import jsonutils

from glare.common import exception
from glare.common import policy
from glare.i18n import _

context_opts = [
    cfg.BoolOpt('allow_anonymous_access', default=False,
                help=_('Allow unauthenticated users to access the API with '
                       'read-only privileges. This only applies when using '
                       'ContextMiddleware.'))
]

CONF = cfg.CONF
CONF.register_opts(context_opts)

LOG = logging.getLogger(__name__)


class RequestContext(context.RequestContext):
    """Stores information about the security context for Glare.

    Stores how the user accesses the system, as well as additional request
    information.
    """

    def __init__(self, service_catalog=None, **kwargs):
        super(RequestContext, self).__init__(**kwargs)
        self.service_catalog = service_catalog
        # check if user is admin using policy file
        if kwargs.get('is_admin') is None:
            self.is_admin = policy.check_is_admin(self)

    def to_dict(self):
        d = super(RequestContext, self).to_dict()
        d.update({
            'service_catalog': self.service_catalog,
        })
        return d

    def to_policy_values(self):
        values = super(RequestContext, self).to_policy_values()
        values['is_admin'] = self.is_admin
        values['read_only'] = self.read_only
        return values


class BaseContextMiddleware(base_middleware.ConfigurableMiddleware):
    @staticmethod
    def process_response(resp, request=None):
        try:
            request_id = resp.request.context.request_id
            # For python 3 compatibility need to use bytes type
            prefix = b'req-' if isinstance(request_id, bytes) else 'req-'

            if not request_id.startswith(prefix):
                request_id = prefix + request_id

            resp.headers['x-openstack-request-id'] = request_id
        except AttributeError:
            pass

        return resp


class ContextMiddleware(BaseContextMiddleware):
    @staticmethod
    def process_request(req):
        """Convert authentication information into a request context.

        Generate a RequestContext object from the available
        authentication headers and store on the 'context' attribute
        of the req object.

        :param req: wsgi request object that will be given the context object
        :raises: webob.exc.HTTPUnauthorized: when value of the
                                            X-Identity-Status  header is not
                                            'Confirmed' and anonymous access
                                            is disallowed
        """
        if req.headers.get('X-Identity-Status') == 'Confirmed':
            req.context = ContextMiddleware._get_authenticated_context(req)
        elif CONF.allow_anonymous_access:
            req.context = RequestContext(read_only=True, is_admin=False)
        else:
            raise exception.Unauthorized()

    @staticmethod
    def _get_authenticated_context(req):
        headers = req.headers
        service_catalog = None
        if headers.get('X-Service-Catalog') is not None:
            catalog_header = headers.get('X-Service-Catalog')
            try:
                service_catalog = jsonutils.loads(catalog_header)
            except ValueError:
                raise exception.GlareException(
                    _('Invalid service catalog json.'))
        kwargs = {
            'service_catalog': service_catalog,
            'request_id': req.environ.get(request_id.ENV_REQUEST_ID),
        }
        return RequestContext.from_environ(req.environ, **kwargs)


class TrustedAuthMiddleware(BaseContextMiddleware):
    @staticmethod
    def process_request(req):
        auth_token = req.headers.get('X-Auth-Token')
        if not auth_token:
            msg = _("Auth token must be provided")
            raise exception.Unauthorized(msg)
        try:
            user, tenant, roles = auth_token.strip().split(':', 3)
        except ValueError:
            msg = _("Wrong auth token format. It must be 'user:tenant:roles'")
            raise exception.Unauthorized(msg)
        if not tenant:
            msg = _("Tenant must be specified in auth token. "
                    "Format of the token is 'user:tenant:roles'")
            raise exception.Unauthorized(msg)
        elif tenant.lower() == 'none':
            tenant = None
            req.headers['X-Identity-Status'] = 'Nope'
        else:
            req.headers['X-Identity-Status'] = 'Confirmed'

        req.headers['X-User-Id'] = user
        req.headers['X-Tenant-Id'] = tenant
        req.headers['X-Roles'] = roles

        if req.headers.get('X-Identity-Status') == 'Confirmed':
            kwargs = {'request_id': req.environ.get(request_id.ENV_REQUEST_ID)}
            req.context = RequestContext.from_environ(req.environ, **kwargs)
        elif CONF.allow_anonymous_access:
            req.context = RequestContext(read_only=True, is_admin=False)
        else:
            raise exception.Unauthorized()
