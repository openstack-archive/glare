# Copyright 2017 OpenStack Foundation.
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

from glare.api.v1 import resource
from glare.tests.unit import base


class TestArtifactAPI(base.BaseTestCase):

    """Test Glare API Controller."""

    def test_create_artifact(self):
        req = self.get_fake_request(user=base.users['user1'])
        values = {'name': 'img', 'version': '1.0',
                  'description': "Test Image", 'tags': ['test'],
                  'metadata': {'type': 'image'}}

        res = resource.ArtifactsController().create(req, 'images', values)
        self.assertEqual('img', res['name'])
        self.assertEqual('1.0.0', res['version'])
        self.assertEqual(base.users['user1']['tenant_id'], res['owner'])
        self.assertEqual('drafted', res['status'])
        self.assertEqual('private', res['visibility'])
        self.assertEqual('Test Image', res['description'])
        self.assertEqual({'type': 'image'}, res['metadata'])

    def test_list_artifacts(self):
        req = self.get_fake_request(user=base.users['user1'])
        res = resource.ArtifactsController().list(req, 'images', [])
        self.assertEqual({'artifacts': [], 'type_name': 'images'}, res)
