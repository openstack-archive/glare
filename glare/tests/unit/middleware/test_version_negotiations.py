# Copyright 2017 - Nokia Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import webob

from glare.api.middleware import version_negotiation
from glare.common import exception as exc
from glare.tests.unit import base


class TestContextMiddleware(base.BaseTestCase):
    MIME_TYPE = 'application/vnd.openstack.artifacts-'

    def _build_request(self, accept, path_info):
        req = webob.Request.blank(path_info)
        req.accept = accept
        return req

    def _build_middleware(self):
        return version_negotiation.GlareVersionNegotiationFilter(None)

    def test_version_request(self):
        _LINKS = [{
            "rel": "describedby",
            "type": "text/html",
            "href": "http://docs.openstack.org/",
        }]
        for path_info in ('/', '/versions'):
            expected = {'versions': [
                {
                    'version': '1.0',
                    'status': 'STABLE',
                    'links': _LINKS,
                    'media-type': 'application/vnd.openstack.artifacts-1.0',
                },
                {
                    'version': '1.1',
                    'status': 'EXPERIMENTAL',
                    'links': _LINKS,
                    'media-type': 'application/vnd.openstack.artifacts-1.1',
                }]
            }
            req = self._build_request(self.MIME_TYPE + '1.0', path_info)
            res = self._build_middleware().process_request(req)
            self.assertEqual(expected, res.json_body)

    def test_wrong_version(self):
        req = self._build_request(self.MIME_TYPE + 'INVALID', '/artifacts')
        self.assertRaises(exc.BadRequest,
                          self._build_middleware().process_request, req)

    def test_too_big_version(self):
        req = self._build_request(self.MIME_TYPE + '10000.0', '/artifacts')
        self.assertRaises(exc.InvalidGlobalAPIVersion,
                          self._build_middleware().process_request, req)

    def test_latest_version(self):
        req = self._build_request(self.MIME_TYPE + 'latest', '/artifacts')
        self._build_middleware().process_request(req)
        self.assertEqual('1.1', req.api_version_request.get_string())

    def test_version_unknown(self):
        req = self._build_request('UNKNOWN', '/artifacts')
        self._build_middleware().process_request(req)
        self.assertEqual('1.0', req.api_version_request.get_string())

    def test_response(self):
        res = webob.Response()
        req = self._build_request('1.0', '/artifacts')
        mw = self._build_middleware()
        mw.process_request(req)
        mw.process_response(res, req)
        self.assertIn('openstack-api-version', res.headers)
        self.assertEqual('artifact 1.0', res.headers['openstack-api-version'])
        self.assertIn('Vary', res.headers)
        self.assertEqual('openstack-api-version', res.headers['Vary'])
