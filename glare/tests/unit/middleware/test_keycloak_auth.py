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

import mock
import requests
import webob

from glare.api.middleware import keycloak_auth
from glare.common import exception as exc
from glare.tests.unit import base


class TestKeycloakAuthMiddleware(base.BaseTestCase):
    def _build_request(self, token):
        req = webob.Request.blank("/")
        req.headers["x-auth-token"] = token
        req.get_response = lambda app: None
        return req

    def _build_middleware(self):
        return keycloak_auth.KeycloakAuthMiddleware(None)

    @mock.patch("requests.get")
    def test_header_parsing(self, mocked_get):
        token = {
            "iss": "http://localhost:8080/auth/realms/my_realm",
            "realm_access": {
                "roles": ["role1", "role2"]
            }
        }
        mocked_resp = mock.Mock()
        mocked_resp.status_code = 200
        mocked_resp.json.return_value = '{"user": "mike"}'
        mocked_get.return_value = mocked_resp

        req = self._build_request(token)
        with mock.patch("jwt.decode", return_value=token):
            self._build_middleware()(req)
        self.assertEqual("Confirmed", req.headers["X-Identity-Status"])
        self.assertEqual("my_realm", req.headers["X-Project-Id"])
        self.assertEqual("role1,role2", req.headers["X-Roles"])

    def test_no_auth_token(self):
        req = webob.Request.blank("/")
        self.assertRaises(exc.Unauthorized, self._build_middleware(), req)

    @mock.patch("requests.get")
    def test_no_realm_access(self, mocked_get):
        token = {
            "iss": "http://localhost:8080/auth/realms/my_realm",
        }
        mocked_resp = mock.Mock()
        mocked_resp.status_code = 200
        mocked_resp.json.return_value = '{"user": "mike"}'
        mocked_get.return_value = mocked_resp

        req = self._build_request(token)
        with mock.patch("jwt.decode", return_value=token):
            self._build_middleware()(req)
        self.assertEqual("Confirmed", req.headers["X-Identity-Status"])
        self.assertEqual("my_realm", req.headers["X-Project-Id"])
        self.assertEqual("", req.headers["X-Roles"])

    def test_wrong_token_format(self):
        req = self._build_request(token="WRONG_FORMAT_TOKEN")
        self.assertRaises(exc.Unauthorized, self._build_middleware(), req)

    @mock.patch("requests.get")
    def test_server_unauthorized(self, mocked_get):
        token = {
            "iss": "http://localhost:8080/auth/realms/my_realm",
        }
        mocked_resp = mock.Mock()
        mocked_resp.status_code = 401
        mocked_resp.json.return_value = '{"user": "mike"}'
        mocked_get.return_value = mocked_resp

        req = self._build_request(token)
        with mock.patch("jwt.decode", return_value=token):
            self.assertRaises(exc.Unauthorized, self._build_middleware(), req)

    @mock.patch("requests.get")
    def test_server_exception(self, mocked_get):
        token = {
            "iss": "http://localhost:8080/auth/realms/my_realm",
        }
        mocked_resp = mock.Mock()
        mocked_resp.status_code = 500
        mocked_resp.json.return_value = '{"user": "mike"}'
        mocked_get.return_value = mocked_resp

        req = self._build_request(token)
        with mock.patch("jwt.decode", return_value=token):
            self.assertRaises(
                exc.GlareException, self._build_middleware(), req)

    @mock.patch("requests.get")
    def test_connection_error(self, mocked_get):
        token = {
            "iss": "http://localhost:8080/auth/realms/my_realm",
        }
        mocked_get.side_effect = requests.ConnectionError

        req = self._build_request(token)
        with mock.patch("jwt.decode", return_value=token):
            self.assertRaises(
                exc.GlareException, self._build_middleware(), req)
