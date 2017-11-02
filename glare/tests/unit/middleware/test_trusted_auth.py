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

from glare.api.middleware import context
from glare.common import exception as exc
from glare.tests.unit import base


class TestTrustedAuthMiddleware(base.BaseTestCase):
    def _build_request(self, token):
        req = webob.Request.blank("/")
        req.headers["x-auth-token"] = token
        req.get_response = lambda app: None
        return req

    def _build_middleware(self):
        return context.TrustedAuthMiddleware(None)

    def test_header_parsing(self):
        token = 'user1:tenant1:role1,role2'
        req = self._build_request(token)
        self._build_middleware().process_request(req)

        self.assertEqual("Confirmed", req.headers["X-Identity-Status"])
        self.assertEqual("user1", req.headers["X-User-Id"])
        self.assertEqual("tenant1", req.headers["X-Tenant-Id"])
        self.assertEqual("role1,role2", req.headers["X-Roles"])

        self.assertEqual(token, req.context.auth_token)
        self.assertEqual('user1', req.context.user)
        self.assertEqual('tenant1', req.context.project_id)
        self.assertEqual(['role1', 'role2'], req.context.roles)
        self.assertIn('service_catalog', req.context.to_dict())

    def test_no_auth_token(self):
        req = self._build_request(None)
        del req.headers['x-auth-token']
        self.assertRaises(exc.Unauthorized,
                          self._build_middleware().process_request, req)

    def test_wrong_format(self):
        req = self._build_request('WRONG_FORMAT')
        middleware = self._build_middleware()
        self.assertRaises(exc.Unauthorized,
                          middleware.process_request, req)

        req = self._build_request('user1:tenant1:role1:role2')
        self.assertRaises(exc.Unauthorized,
                          middleware.process_request, req)

    def test_no_tenant(self):
        req = self._build_request('user1::role')
        middleware = self._build_middleware()
        self.assertRaises(exc.Unauthorized,
                          middleware.process_request, req)

    def test_no_roles(self):
        # stripping extra spaces in request
        req = self._build_request('user1:tenant1:')
        self._build_middleware().process_request(req)
        self.assertFalse(req.context.is_admin)
        self.assertEqual('user1', req.context.user)
        self.assertEqual("user1", req.headers["X-User-Id"])
        self.assertEqual("", req.headers["X-Roles"])
        self.assertEqual([], req.context.roles)

    def test_is_admin_flag(self):
        # is_admin check should look for 'admin' role by default
        req = self._build_request('user1:tenant1:role1,admin')
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

        # without the 'admin' role, is_admin should be False
        req = self._build_request('user1:tenant1:role1,role2')
        self._build_middleware().process_request(req)
        self.assertFalse(req.context.is_admin)

        # if we change the admin_role attribute, we should be able to use it
        req = self._build_request('user1:tenant1:role1,role2')
        self.policy({'context_is_admin': 'role:role1'})
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

    def test_roles_case_insensitive(self):
        # accept role from request
        req = self._build_request('user1:tenant1:Admin,role2')
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

        # accept role from config
        req = self._build_request('user1:tenant1:role1,role2')
        self.policy({'context_is_admin': 'role:rOLe1'})
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)

    def test_token_stripping(self):
        # stripping extra spaces in request
        req = self._build_request('   user1:tenant1:role1\t')
        self.policy({'context_is_admin': 'role:role1'})
        self._build_middleware().process_request(req)
        self.assertTrue(req.context.is_admin)
        self.assertEqual('user1', req.context.user)
        self.assertEqual("user1", req.headers["X-User-Id"])
        self.assertEqual("role1", req.headers["X-Roles"])

    def test_anonymous_access_enabled(self):
        req = self._build_request('user1:none:role1,role2')
        self.config(allow_anonymous_access=True)
        middleware = self._build_middleware()
        middleware.process_request(req)
        self.assertIsNone(req.context.auth_token)
        self.assertIsNone(req.context.user)
        self.assertIsNone(req.context.project_id)
        self.assertEqual([], req.context.roles)
        self.assertFalse(req.context.is_admin)
        self.assertTrue(req.context.read_only)

    def test_anonymous_access_defaults_to_disabled(self):
        req = self._build_request('user1:none:role1,role2')
        middleware = self._build_middleware()
        self.assertRaises(exc.Unauthorized,
                          middleware.process_request, req)

    def test_response(self):
        req = self._build_request('user1:tenant1:role1,role2')
        req.context = context.RequestContext()
        request_id = req.context.request_id

        resp = webob.Response()
        resp.request = req
        self._build_middleware().process_response(resp)
        self.assertEqual(request_id, resp.headers['x-openstack-request-id'])
        resp_req_id = resp.headers['x-openstack-request-id']
        # Validate that request-id do not starts with 'req-req-'
        if isinstance(resp_req_id, bytes):
            resp_req_id = resp_req_id.decode('utf-8')
        self.assertFalse(resp_req_id.startswith('req-req-'))
        self.assertTrue(resp_req_id.startswith('req-'))

    def test_response_no_request_id(self):
        req = self._build_request('user1:tenant1:role1,role2')
        req.context = context.RequestContext()
        del req.context.request_id

        resp = webob.Response()
        resp.request = req
        self._build_middleware().process_response(resp)
        self.assertNotIn('x-openstack-request-id', resp.headers)

    def test_response_no_request_id_prefix(self):
        # prefix is 'req-'
        req = self._build_request('user1:tenant1:role1,role2')
        req.context = context.RequestContext()
        req.context.request_id = "STRING_WITH_NO_PREFIX"

        resp = webob.Response()
        resp.request = req
        self._build_middleware().process_response(resp)
        self.assertEqual('req-STRING_WITH_NO_PREFIX',
                         resp.headers['x-openstack-request-id'])
