# Copyright 2018 - Red Hat
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

from glare.common import exception as exc
from glare.tests.unit import base


class TestPolicies(base.BaseTestArtifactAPI):
    """Test glare policies."""

    def test_disable_type_list_api(self):

        # type list enabled by default for all users
        self.controller.list_type_schemas(self.req)

        # disable type list for regular users
        rule = {"artifact:type_list": "rule:context_is_admin"}
        self.policy(rule)

        # now glare returns PolicyException if a user tries to get the
        # list of artifact types.
        self.assertRaises(exc.PolicyException,
                          self.controller.list_type_schemas, self.req)

        # admin still can receive the list
        admin_req = self.get_fake_request(user=self.users['admin'])
        self.controller.list_type_schemas(admin_req)

        # completely disable the api for all users
        rule = {"artifact:type_list": "!"}
        self.policy(rule)

        self.assertRaises(exc.PolicyException,
                          self.controller.list_type_schemas, self.req)
        self.assertRaises(exc.PolicyException,
                          self.controller.list_type_schemas, admin_req)
