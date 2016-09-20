# Copyright 2011 OpenStack Foundation
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

"""
A filter middleware that inspects the requested URI for a version string
and/or Accept headers and attempts to negotiate an API controller to
return
"""

import microversion_parse
from oslo_log import log as logging
from oslo_middleware import base as base_middleware


from glare.api.v1 import api_version_request as api_version
from glare.api import versions as artifacts_versions
from glare.common import exception

LOG = logging.getLogger(__name__)


def get_version_from_accept(accept_header, vnd_mime_type):
        """Try to parse accept header to extract api version

        :param accept_header: accept header
        :return: version string in the request or None if not specified
        """
        accept = str(accept_header)
        if accept.startswith(vnd_mime_type):
            LOG.debug("Using media-type versioning")
            token_loc = len(vnd_mime_type)
            return accept[token_loc:]
        else:
            return None


class GlareVersionNegotiationFilter(base_middleware.ConfigurableMiddleware):
    """Middleware that defines API version in request and redirects it
    to correct Router.
    """

    SERVICE_TYPE = 'artifact'
    MIME_TYPE = 'application/vnd.openstack.artifacts-'

    @staticmethod
    def process_request(req):
        """Process api request:
        1. Define if this is request for available versions or not
        2. If it is not version request check extract version
        3. Validate available version and add version info to request
        """

        args = {'method': req.method, 'path': req.path, 'accept': req.accept}
        LOG.debug("Determining version of request: %(method)s %(path)s "
                  "Accept: %(accept)s", args)

        # determine if this is request for versions
        if req.path_info in ('/versions', '/'):
            is_multi = req.path_info == '/'
            return artifacts_versions.Controller.index(
                req, is_multi=is_multi)

        # determine api version from request
        req_version = get_version_from_accept(
            req.accept, GlareVersionNegotiationFilter.MIME_TYPE)
        if req_version is None:
            # determine api version from microversion header
            LOG.debug("Determine version from microversion header.")
            req_version = microversion_parse.get_version(
                req.headers,
                service_type=GlareVersionNegotiationFilter.SERVICE_TYPE)

        # validate microversions header
        req.api_version_request = \
            GlareVersionNegotiationFilter._get_api_version_request(
                req_version)
        req_version = req.api_version_request.get_string()

        LOG.debug("Matched version: %s", req_version)
        LOG.debug('new path %s', req.path_info)

    @staticmethod
    def _get_api_version_request(req_version):
        """Set API version for request based on the version header string."""
        if req_version is None:
            LOG.debug("No API version in request header. Use default version.")
            cur_ver = api_version.APIVersionRequest.default_version()
        elif req_version == 'latest':
            # 'latest' is a special keyword which is equivalent to
            # requesting the maximum version of the API supported
            cur_ver = api_version.APIVersionRequest.max_version()
        else:
            cur_ver = api_version.APIVersionRequest(req_version)

        # Check that the version requested is within the global
        # minimum/maximum of supported API versions
        if not cur_ver.matches(cur_ver.min_version(), cur_ver.max_version()):
            raise exception.InvalidGlobalAPIVersion(
                req_ver=cur_ver.get_string(),
                min_ver=cur_ver.min_version().get_string(),
                max_ver=cur_ver.max_version().get_string())
        return cur_ver

    @staticmethod
    def process_response(response, request=None):
        if hasattr(response, 'headers'):
            if hasattr(request, 'api_version_request'):
                api_header_name = microversion_parse.STANDARD_HEADER
                response.headers[api_header_name] = (
                    GlareVersionNegotiationFilter.SERVICE_TYPE + ' ' +
                    request.api_version_request.get_string())
                response.headers.add('Vary', api_header_name)

        return response
