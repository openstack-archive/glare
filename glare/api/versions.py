# Copyright 2012 OpenStack Foundation.
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
from oslo_serialization import jsonutils
from six.moves import http_client
import webob.dec

from glare.api.v1 import api_version_request
from glare.i18n import _


versions_opts = [
    cfg.StrOpt('public_endpoint',
               help=_("""
Public url endpoint to use for Glare versions response.

This is the public url endpoint that will appear in the Glare
"versions" response. If no value is specified, the endpoint that is
displayed in the version's response is that of the host running the
API service. Change the endpoint to represent the proxy URL if the
API service is running behind a proxy. If the service is running
behind a load balancer, add the load balancer's URL for this value.

Services which consume this:
    * glare

Possible values:
    * None
    * Proxy URL
    * Load balancer URL

Related options:
    * None

""")),
]


CONF = cfg.CONF
CONF.register_opts(versions_opts)


class Controller(object):

    """A controller that reports which API versions are supported."""

    @staticmethod
    def index(req, is_multi):
        """Respond to a request for all OpenStack API versions.
        :param is_multi: defines if multiple choices should be response status
        or not
        :param req: user request object
        :return list of supported API versions
        """
        def build_version_object(max_version, min_version, status, path=None):
            url = CONF.public_endpoint or req.host_url
            return {
                'id': 'v%s' % max_version,
                'links': [
                    {
                        'rel': 'self',
                        'href': '%s/%s/' % (url, path) if path else
                        '%s/' % url,
                    },
                ],
                'status': status,
                'min_version': min_version,
                'version': max_version
            }

        microv_max = api_version_request.APIVersionRequest.max_version()
        microv_min = api_version_request.APIVersionRequest.min_version()
        version_objs = [build_version_object(microv_max.get_string(),
                                             microv_min.get_string(),
                                             'EXPERIMENTAL')]
        return_status = (http_client.MULTIPLE_CHOICES if is_multi else
                         http_client.OK)
        response = webob.Response(request=req,
                                  status=return_status,
                                  content_type='application/json')
        response.body = jsonutils.dump_as_bytes(dict(versions=version_objs))
        return response
