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

from glare.common import exception as exc
from glare.tests.unit import base


class TestArtifactCreate(base.BaseTestArtifactAPI):

    """Test Glare artifact creation."""

    def test_create_artifact_minimal(self):

        for name in ['ttt', 'tt:t', 'tt t', 'tt: t', 'tt,t']:
            values = {'name': name}

            res = self.controller.create(self.req, 'sample_artifact', values)
            self.assertEqual(name, res['name'])
            self.assertEqual('0.0.0', res['version'])
            self.assertEqual(self.users['user1']['tenant_id'], res['owner'])
            self.assertEqual('drafted', res['status'])
            self.assertEqual('private', res['visibility'])
            self.assertEqual('', res['description'])
            self.assertEqual({}, res['metadata'])
            self.assertEqual([], res['tags'])

    def test_create_artifact_with_version(self):
        values = {'name': 'name', 'version': '1.0'}
        res = self.controller.create(self.req, 'sample_artifact', values)
        self.assertEqual('name', res['name'])
        self.assertEqual('1.0.0', res['version'])

        values = {'name': 'name', 'version': '1:0'}
        res = self.controller.create(self.req, 'sample_artifact', values)
        self.assertEqual('1.0.0-0', res['version'])

        values = {'name': 'name', 'version': '1:0:0'}
        res = self.controller.create(self.req, 'sample_artifact', values)
        self.assertEqual('1.0.0-0-0', res['version'])

        values = {'name': 'name', 'version': '2:0-0'}
        res = self.controller.create(self.req, 'sample_artifact', values)
        self.assertEqual('2.0.0-0-0', res['version'])

    def test_create_artifact_with_fields(self):
        values = {'name': 'ttt', 'version': '1.0',
                  'description': "Test Artifact", 'tags': ['a', 'a', 'b'],
                  'metadata': {'type': 'image'}}

        res = self.controller.create(self.req, 'sample_artifact', values)
        self.assertEqual('ttt', res['name'])
        self.assertEqual('1.0.0', res['version'])
        self.assertEqual(self.users['user1']['tenant_id'], res['owner'])
        self.assertEqual('drafted', res['status'])
        self.assertEqual('private', res['visibility'])
        self.assertEqual('Test Artifact', res['description'])
        self.assertEqual({'type': 'image'}, res['metadata'])
        self.assertEqual({'a', 'b'}, set(res['tags']))

    def test_create_no_artifact_type(self):
        values = {'name': 'ttt'}

        self.assertRaises(exc.NotFound, self.controller.create,
                          self.req, 'wrong_type', values)

    def test_create_artifact_no_name(self):
        values = {'version': '1.0'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_wrong_parameters(self):
        values = {'name': 'test', 'version': 'invalid_format'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'version': -1}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'version': ':'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': '', 'version': '1.0'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'a' * 256}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'description': 'a' * 4097}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'tags': ['a' * 256]}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'tags': ['']}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'tags': ['a/a']}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'tags': ['a,a']}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'tags': [str(i) for i in range(256)]}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'metadata': {'key': 'a' * 256}}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'metadata': {'': 'a'}}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'metadata': {'a' * 256: 'a'}}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test',
                  'metadata': {('a' + str(i)): 'a' for i in range(256)}}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_not_existing_field(self):
        values = {'name': 'test', 'not_exist': 'some_value'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', '': 'a'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_with_nullable_false_field(self):
        values = {'name': 'art1', 'int_not_nullable_without_default': 1}

        res = self.controller.create(self.req,
                                     'non_nullable_fields_artifact', values)
        self.assertEqual(1, res['int_not_nullable_without_default'])
        self.assertEqual(0, res['int_not_nullable_with_default'])

        values = {'name': 'art2'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'non_nullable_fields_artifact', values)

    def test_create_artifact_blob(self):
        values = {'name': 'test', 'blob': 'DATA'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_system_fields(self):
        values = {'name': 'test',
                  'id': '5fdeba9a-ba12-4147-bb8a-a8daada84222'}
        self.assertRaises(exc.Forbidden, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'created_at': '2000-01-01'}
        self.assertRaises(exc.Forbidden, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'updated_at': '2000-01-01'}
        self.assertRaises(exc.Forbidden, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'activated_at': '2000-01-01'}
        self.assertRaises(exc.Forbidden, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'owner': 'new_owner'}
        self.assertRaises(exc.Forbidden, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_status_and_visibility(self):
        values = {'name': 'test', 'status': 'activated'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

        values = {'name': 'test', 'visibility': 'public'}
        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'sample_artifact', values)

    def test_create_artifact_unicode(self):
        name = u'\u0442\u0435\u0441\u0442'
        description = u'\u041E\u043F\u0438\u0441\u0430\u043D\u0438\u0435'
        tags = [u'\u041C\u0435\u0442\u043A\u0430']
        metadata = {'key': u'\u0417\u043D\u0430\u0447\u0435\u043D\u0438\u0435'}
        values = {
            'name': name,
            'version': '1.0',
            'description': description,
            'tags': tags,
            'metadata': metadata
        }

        res = self.controller.create(self.req, 'images', values)
        self.assertEqual(name, res['name'])
        self.assertEqual('1.0.0', res['version'])
        self.assertEqual(self.users['user1']['tenant_id'], res['owner'])
        self.assertEqual('drafted', res['status'])
        self.assertEqual('private', res['visibility'])
        self.assertEqual(description, res['description'])
        self.assertEqual(metadata, res['metadata'])
        self.assertEqual(tags, res['tags'])

    def test_create_artifact_4_byte_unicode(self):
        bad_name = u'A name with forbidden symbol \U0001f62a'
        values = {
            'name': bad_name,
            'version': '1.0',
        }

        self.assertRaises(exc.BadRequest, self.controller.create,
                          self.req, 'images', values)
