# Copyright 2016 OpenStack Foundation.
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

from oslo_serialization import jsonutils
import webob

from glare.api import versions
from glare.tests.unit import base


class VersionsTest(base.BaseTestCase):

    """Test the version information returned from the API service."""

    def test_root_endpoint(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9494/')
        req.accept = 'application/json'
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {'links': [{'href': 'http://docs.openstack.org/',
                        'rel': 'describedby',
                        'type': 'text/html'}],
             'media-type': 'application/vnd.openstack.artifacts-1.0',
             'status': 'STABLE',
             'version': '1.0'},
            {'links': [{'href': 'http://docs.openstack.org/',
                        'rel': 'describedby',
                        'type': 'text/html'}],
             'media-type': 'application/vnd.openstack.artifacts-1.1',
             'status': 'EXPERIMENTAL',
             'version': '1.1'}]
        self.assertEqual(expected, results)

    def test_versions_endpoint(self):
        req = webob.Request.blank('/versions',
                                  base_url='http://127.0.0.1:9494/')
        req.accept = 'application/json'
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {'links': [{'href': 'http://docs.openstack.org/',
                        'rel': 'describedby',
                        'type': 'text/html'}],
             'media-type': 'application/vnd.openstack.artifacts-1.0',
             'status': 'STABLE',
             'version': '1.0'},
            {'links': [{'href': 'http://docs.openstack.org/',
                        'rel': 'describedby',
                        'type': 'text/html'}],
             'media-type': 'application/vnd.openstack.artifacts-1.1',
             'status': 'EXPERIMENTAL',
             'version': '1.1'}]
        self.assertEqual(expected, results)
