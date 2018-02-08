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
from io import BytesIO

from glare.common import exception as exc
from glare.common import store_api

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

    def test_list_all_artifacts(self):

        # create artifacts with user1 and user 2
        user1_req = self.get_fake_request(user=self.users['user1'])
        user2_req = self.get_fake_request(user=self.users['user2'])

        for i in range(5):
            self.controller.create(user1_req, 'sample_artifact',
                                   {'name': 'user1%s' % i,
                                    'version': '%d.0' % i})

            self.controller.create(user2_req, 'sample_artifact',
                                   {'name': 'user2%s' % i,
                                    'version': '%d.0' % i})

        # user1 list only its realm artifacts
        user1_art_list = self.controller.list(user1_req, 'sample_artifact')
        self.assertEqual(5, len(user1_art_list["artifacts"]))

        # user2 list only it's realm artifact
        user2_art_list = self.controller.list(user2_req, 'sample_artifact')
        self.assertEqual(5, len(user2_art_list["artifacts"]))

        # enable to list all arts from all realms for a user with role su_role
        rule = {"artifact:list_all_artifacts": "role:su_role"}
        self.policy(rule)

        # Append su_role to 'user1'
        self.users['user1']['roles'].append("su_role")
        list_all_art = self.controller.list(user1_req, "sample_artifact")

        # now glare returns all the artifacts (from all the realms)
        self.assertEqual(10, len(list_all_art["artifacts"]))

    def test_get_any_artifact(self):

        # create artifacts with user1 and user 2
        user1_req = self.get_fake_request(user=self.users['user1'])
        user2_req = self.get_fake_request(user=self.users['user2'])

        art1 = self.controller.create(user1_req, 'sample_artifact',
                                      {'name': 'user1%s' % 1,
                                       'version': '%d.0' % 1})

        art2 = self.controller.create(user2_req, 'sample_artifact',
                                      {'name': 'user2%s' % 2,
                                       'version': '%d.0' % 2})

        # user1 can get artifacts from its realm
        self.controller.show(user1_req, 'sample_artifact', art1['id'])

        # user1 cannot get artifacts from other realm
        self.assertRaises(exc.NotFound, self.controller.show, user1_req,
                          'sample_artifact', art2['id'])

        # get_any_artifact
        rule = {"artifact:get_any_artifact": "role:su_role"}
        self.policy(rule)

        # user2 can get artifact from his realm only
        self.controller.show(user2_req, 'sample_artifact', art2['id'])
        self.assertRaises(exc.NotFound, self.controller.show, user2_req,
                          'sample_artifact', art1['id'])

        # Append su_role to 'user1'
        self.users['user1']['roles'].append("su_role")

        # Now user1 can get artifact from other realm
        self.controller.show(user1_req, 'sample_artifact', art2['id'])

    def test_download_from_any_artifact(self):

        # create artifacts with user1 and user 2
        user1_req = self.get_fake_request(user=self.users['user1'])
        user2_req = self.get_fake_request(user=self.users['user2'])

        art1 = self.controller.create(user1_req, 'sample_artifact',
                                      {'name': 'user1%s' % 1,
                                       'version': '%d.0' % 1})

        art2 = self.controller.create(user2_req, 'sample_artifact',
                                      {'name': 'user2%s' % 2,
                                       'version': '%d.0' % 2})

        # Upload blobs
        self.controller.upload_blob(
            user1_req, 'sample_artifact', art1['id'], 'blob',
            BytesIO(b'a' * 100), 'application/octet-stream')

        self.controller.upload_blob(
            user2_req, 'sample_artifact', art2['id'], 'blob',
            BytesIO(b'a' * 50), 'application/octet-stream')

        # Download blobs
        flobj1 = self.controller.download_blob(
            user1_req, 'sample_artifact', art1['id'], 'blob')
        self.assertEqual(b'a' * 100, store_api.read_data(flobj1['data']))

        flobj2 = self.controller.download_blob(
            user2_req, 'sample_artifact', art2['id'], 'blob')
        self.assertEqual(b'a' * 50, store_api.read_data(flobj2['data']))

        # Make sure user2 cannot download blob from artifact in realm1
        self.assertRaises(exc.NotFound, self.controller.download_blob,
                          user2_req, 'sample_artifact', art1['id'], 'blob')

        #  Add role def to policy
        rule = {"artifact:download_from_any_artifact": "role:su_role"}
        self.policy(rule)

        # Make sure user1 cannot download blob from artifact in realm2
        self.assertRaises(exc.NotFound, self.controller.download_blob,
                          user1_req, 'sample_artifact', art2['id'], 'blob')

        # Append su_role to 'user1'
        self.users['user1']['roles'].append("su_role")

        # Now user1 can get download blob from other realm
        flobj2 = self.controller.download_blob(
            user1_req, 'sample_artifact', art2['id'], 'blob')
        self.assertEqual(b'a' * 50, store_api.read_data(flobj2['data']))

        # User2 still cannot download blob from artifact in realm1
        self.assertRaises(exc.NotFound, self.controller.download_blob,
                          user2_req, 'sample_artifact', art1['id'], 'blob')
