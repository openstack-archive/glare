# Copyright 2016 OpenStack Foundation
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

"""A middleware that turns exceptions into parsable string.
Inspired by Cinder's and Heat't faultwrapper.
"""

import sys
import traceback

from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import base as base_middleware
from oslo_utils import reflection
import six
import webob.dec
import webob.exc

from glare.common import exception
from glare.common import wsgi


LOG = logging.getLogger(__name__)


class Fault(object):

    def __init__(self, error):
        self.error = error

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        serializer = wsgi.JSONResponseSerializer()
        resp = webob.Response(request=req)
        default_webob_exc = webob.exc.HTTPInternalServerError()
        resp.status_code = self.error.get('code', default_webob_exc.code)
        serializer.default(resp, self.error)
        return resp


class GlareFaultWrapperFilter(base_middleware.ConfigurableMiddleware):
    """Replace error body with something the client can parse."""
    error_map = {
        'BadRequest': webob.exc.HTTPBadRequest,
        'Unauthorized': webob.exc.HTTPUnauthorized,
        'Forbidden': webob.exc.HTTPForbidden,
        'NotFound': webob.exc.HTTPNotFound,
        'RequestTimeout': webob.exc.HTTPRequestTimeout,
        'Conflict': webob.exc.HTTPConflict,
        'Gone': webob.exc.HTTPGone,
        'PreconditionFailed': webob.exc.HTTPPreconditionFailed,
        'RequestEntityTooLarge': webob.exc.HTTPRequestEntityTooLarge,
        'UnsupportedMediaType': webob.exc.HTTPUnsupportedMediaType,
        'RequestRangeNotSatisfiable': webob.exc.HTTPRequestRangeNotSatisfiable,
        'Locked': webob.exc.HTTPLocked,
        'FailedDependency': webob.exc.HTTPFailedDependency,
        'NotAcceptable': webob.exc.HTTPNotAcceptable,
        'Exception': webob.exc.HTTPInternalServerError,
    }

    def _map_exception_to_error(self, class_exception):
        if class_exception.__name__ not in self.error_map:
            return self._map_exception_to_error(class_exception.__base__)

        return self.error_map[class_exception.__name__]

    def _error(self, ex):
        traceback_marker = 'Traceback (most recent call last)'
        webob_exc = None

        ex_type = reflection.get_class_name(ex, fully_qualified=False)

        full_message = six.text_type(ex)
        if traceback_marker in full_message:
            message, msg_trace = full_message.split(traceback_marker, 1)
            message = message.rstrip('\n')
            msg_trace = traceback_marker + msg_trace
        else:
            msg_trace = 'None\n'
            if sys.exc_info() != (None, None, None):
                msg_trace = traceback.format_exc()
            message = full_message

        if isinstance(ex, exception.GlareException):
            message = six.text_type(ex)

        if not webob_exc:
            webob_exc = self._map_exception_to_error(ex.__class__)

        error = {
            'code': webob_exc.code,
            'title': webob_exc.title,
            'explanation': webob_exc.explanation,
            'error': {
                'message': message,
                'type': ex_type,
            }
        }

        if cfg.CONF.debug:
            error['error']['traceback'] = msg_trace

        # add microversion header is this is not acceptable request
        if isinstance(ex, exception.InvalidGlobalAPIVersion):
            error['min_version'] = ex.kwargs['min_ver']
            error['max_version'] = ex.kwargs['max_ver']

        return error

    @webob.dec.wsgify
    def __call__(self, req):
        try:
            return req.get_response(self.application)
        except Exception as exc:
            LOG.exception(exc)
            return req.get_response(Fault(self._error(exc)))
