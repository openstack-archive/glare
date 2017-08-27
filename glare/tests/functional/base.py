# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from oslo_serialization import jsonutils
from oslo_utils import uuidutils
import requests

from glare.tests import functional


def sort_results(lst, target='name'):
    return sorted(lst, key=lambda x: x[target])


class TestArtifact(functional.FunctionalTest):
    enabled_types = (u'sample_artifact', u'images', u'heat_templates',
                     u'heat_environments', u'tosca_templates',
                     u'murano_packages', u'all')

    users = {
        'user1': {
            'id': uuidutils.generate_uuid(),
            'tenant_id': uuidutils.generate_uuid(),
            'token': uuidutils.generate_uuid(),
            'role': 'member'
        },
        'user2': {
            'id': uuidutils.generate_uuid(),
            'tenant_id': uuidutils.generate_uuid(),
            'token': uuidutils.generate_uuid(),
            'role': 'member'
        },
        'admin': {
            'id': uuidutils.generate_uuid(),
            'tenant_id': uuidutils.generate_uuid(),
            'token': uuidutils.generate_uuid(),
            'role': 'admin'
        },
        'anonymous': {
            'id': None,
            'tenant_id': None,
            'token': None,
            'role': None
        }
    }

    def setUp(self):
        super(TestArtifact, self).setUp()

        self.set_user('user1')
        self.glare_server.deployment_flavor = 'noauth'

        self.glare_server.enabled_artifact_types = ','.join(
            self.enabled_types)
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')
        self.start_servers(**self.__dict__.copy())

    def tearDown(self):
        self.stop_servers()
        self._reset_database(self.glare_server.sql_connection)
        super(TestArtifact, self).tearDown()

    def _url(self, path):
        if path.startswith('/schemas') or \
                path.startswith('/quotas') or \
                path.startswith('/project-quotas'):
            return 'http://127.0.0.1:%d%s' % (self.glare_port, path)
        else:
            return 'http://127.0.0.1:%d/artifacts%s' % (self.glare_port, path)

    def set_user(self, username):
        if username not in self.users:
            raise KeyError
        self.current_user = username

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': self.users[self.current_user]['token'],
            'X-User-Id': self.users[self.current_user]['id'],
            'X-Tenant-Id': self.users[self.current_user]['tenant_id'],
            'X-Project-Id': self.users[self.current_user]['tenant_id'],
            'X-Roles': self.users[self.current_user]['role'],
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def create_artifact(self, data=None, status=201,
                        type_name='sample_artifact'):
        return self.post('/' + type_name, data or {}, status=status)

    def _check_artifact_method(self, method, url, data=None, status=200,
                               headers=None):
        if not headers:
            headers = self._headers()
        else:
            headers = self._headers(headers)
        headers.setdefault("Content-Type", "application/json")
        if 'application/json' in headers['Content-Type'] and data is not None:
            data = jsonutils.dumps(data)
        response = getattr(requests, method)(self._url(url), headers=headers,
                                             data=data)
        self.assertEqual(status, response.status_code, response.text)
        if status >= 400:
            return response.text
        if ("application/json" in response.headers["content-type"] or
                "application/schema+json" in response.headers["content-type"]):
            return jsonutils.loads(response.text)
        return response.text

    def post(self, url, data=None, status=201, headers=None):
        return self._check_artifact_method("post", url, data, status=status,
                                           headers=headers)

    def get(self, url, status=200, headers=None):
        return self._check_artifact_method("get", url, status=status,
                                           headers=headers)

    def delete(self, url, status=204, headers=None):
        return self._check_artifact_method("delete", url, status=status,
                                           headers=headers)

    def patch(self, url, data, status=200, headers=None):
        if headers is None:
            headers = {}
        if 'Content-Type' not in headers:
            headers.update({'Content-Type': 'application/json-patch+json'})
        return self._check_artifact_method("patch", url, data, status=status,
                                           headers=headers)

    def put(self, url, data=None, status=200, headers=None):
        return self._check_artifact_method("put", url, data, status=status,
                                           headers=headers)

    # the test cases below are written in accordance with use cases
    # each test tries to cover separate use case in Glare
    # all code inside each test tries to cover all operators and data
    # involved in use case execution
    # each tests represents part of artifact lifecycle
    # so we can easily define where is the failed code

    make_active = [{"op": "replace", "path": "/status", "value": "active"}]
    make_deactivated = [{"op": "replace", "path": "/status",
                         "value": "deactivated"}]
    make_public = [{"op": "replace", "path": "/visibility", "value": "public"}]

    def admin_action(self, artifact_id, body, status=200,
                     type_name='sample_artifact'):
        cur_user = self.current_user
        self.set_user('admin')
        url = '/%s/%s' % (type_name, artifact_id)
        af = self.patch(url=url, data=body, status=status)
        self.set_user(cur_user)
        return af
