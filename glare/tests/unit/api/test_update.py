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


class TestArtifactUpdate(base.BaseTestArtifactAPI):

    """Test Glare artifact updates."""

    def setUp(self):
        super(TestArtifactUpdate, self).setUp()
        values = {'name': 'ttt', 'version': '1.0'}
        self.sample_artifact = self.controller.create(
            self.req, 'sample_artifact', values)

    def test_basic_update(self):
        changes = [
            {'op': 'replace', 'path': '/name', 'value': 'new_name'},
            {'op': 'replace', 'path': '/version', 'value': '1.0.0'},
            {'op': 'replace', 'path': '/description', 'value': 'Test'},
            {'op': 'replace', 'path': '/tags', 'value': ['tag1', 'tag2']},
            {'op': 'replace', 'path': '/metadata', 'value': {'k': 'v'}},
        ]
        res = self.update_with_values(changes)
        self.assertEqual('new_name', res['name'])
        self.assertEqual('1.0.0', res['version'])
        self.assertEqual('Test', res['description'])
        self.assertEqual({'tag1', 'tag2'}, set(res['tags']))
        self.assertEqual({'k': 'v'}, res['metadata'])

    def test_update_no_artifact_type(self):
        changes = [{'op': 'replace', 'path': '/name', 'value': 'new_name'}]
        self.update_with_values(
            changes, exc_class=exc.NotFound, art_type='wrong_type')

    def test_update_lists(self):
        changes = [{'op': 'replace', 'path': '/list_of_str',
                    'value': ['val1', 'val2']}]
        res = self.update_with_values(changes)
        self.assertEqual({'val1', 'val2'}, set(res['list_of_str']))

        changes = [{'op': 'remove', 'path': '/list_of_str/0'}]
        res = self.update_with_values(changes)
        self.assertEqual(['val2'], res['list_of_str'])

        changes = [{'op': 'replace', 'path': '/list_of_str', 'value': None}]
        res = self.update_with_values(changes)
        self.assertEqual([], res['list_of_str'])

        changes = [{'op': 'add', 'path': '/list_of_str/-', 'value': 'val1'}]
        res = self.update_with_values(changes)
        self.assertEqual(['val1'], res['list_of_str'])

        changes = [{'op': 'replace', 'path': '/list_of_str/0',
                    'value': 'val2'}]
        res = self.update_with_values(changes)
        self.assertEqual(['val2'], res['list_of_str'])

        changes = [{'op': 'replace', 'path': '/list_of_str', 'value': []}]
        res = self.update_with_values(changes)
        self.assertEqual([], res['list_of_str'])

        changes = [{'op': 'replace', 'path': '/list_of_str', 'value': {}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/list_of_str',
                    'value': {'a': 'b'}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/list_of_str',
                    'value': [['a']]}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_dicts(self):
        changes = [{'op': 'replace', 'path': '/dict_of_str',
                    'value': {'k1': 'v1', 'k2': 'v2'}}]
        res = self.update_with_values(changes)
        self.assertEqual({'k1': 'v1', 'k2': 'v2'}, res['dict_of_str'])

        changes = [{'op': 'remove', 'path': '/dict_of_str/k1'}]
        res = self.update_with_values(changes)
        self.assertEqual({'k2': 'v2'}, res['dict_of_str'])

        changes = [{'op': 'replace', 'path': '/dict_of_str', 'value': None}]
        res = self.update_with_values(changes)
        self.assertEqual({}, res['dict_of_str'])

        changes = [{'op': 'add', 'path': '/dict_of_str/k1', 'value': 'v1'}]
        res = self.update_with_values(changes)
        self.assertEqual({'k1': 'v1'}, res['dict_of_str'])

        changes = [{'op': 'replace', 'path': '/dict_of_str/k1',
                    'value': 'v2'}]
        res = self.update_with_values(changes)
        self.assertEqual({'k1': 'v2'}, res['dict_of_str'])

        changes = [{'op': 'replace', 'path': '/dict_of_str', 'value': {}}]
        res = self.update_with_values(changes)
        self.assertEqual({}, res['dict_of_str'])

        changes = [{'op': 'replace', 'path': '/dict_of_str', 'value': []}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/dict_of_str',
                    'value': ['a']}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/dict_of_str/k10',
                    'value': {'k100': 'v100'}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_wrong_parameters(self):
        changes = [{'op': 'replace', 'path': '/name', 'value': ''}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/name', 'value': 'a' * 256}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/version', 'value': ''}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/version', 'value': 'invalid'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/version', 'value': -1}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/description',
                    'value': 'a' * 4097}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/tags', 'value': ['a' * 256]}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/tags', 'value': ['']}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/tags', 'value': ['a/a']}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/tags', 'value': ['a,a']}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/tags',
                    'value': [str(i) for i in range(256)]}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/metadata',
                    'value': {'key': 'a' * 256}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/metadata',
                    'value': {'': 'a'}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/metadata',
                    'value': {'a' * 256: 'a'}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/metadata',
                    'value': {('a' + str(i)): 'a' for i in range(256)}}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_not_existing_field(self):
        changes = [{'op': 'replace', 'path': '/wrong_field', 'value': 'a'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/', 'value': 'a'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_blob(self):
        changes = [{'op': 'replace', 'path': '/blob', 'value': 'a'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_system_fields(self):
        changes = [{'op': 'replace', 'path': '/id',
                    'value': '5fdeba9a-ba12-4147-bb8a-a8daada84222'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/created_at',
                    'value': '2000-01-01'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/updated_at',
                    'value': '2000-01-01'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/activated_at',
                    'value': '2000-01-01'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/owner', 'value': 'new_owner'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/system_attribute',
                    'value': 'some_value'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

    def test_update_artifact_visibility(self):
        self.req = self.get_fake_request(user=self.users['admin'])

        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': 'wrong_value'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': 'public'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': None}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/string_required',
                    'value': 'some_string'}]
        res = self.update_with_values(changes)
        self.assertEqual('some_string', res['string_required'])

        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        res = self.update_with_values(changes)
        self.assertEqual('active', res['status'])

        changes = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        res = self.update_with_values(changes)
        self.assertEqual('public', res['visibility'])

        changes = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        res = self.update_with_values(changes)
        self.assertEqual('public', res['visibility'])

        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': 'private'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_status(self):
        self.req = self.get_fake_request(user=self.users['admin'])

        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'wrong_value'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'deactivated'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'active'}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/status',
                    'value': None}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

        changes = [{'op': 'replace', 'path': '/string_required',
                    'value': 'some_string'}]
        res = self.update_with_values(changes)
        self.assertEqual('some_string', res['string_required'])

        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        res = self.update_with_values(changes)
        self.assertEqual('active', res['status'])

        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        res = self.update_with_values(changes)
        self.assertEqual('active', res['status'])

        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'deactivated'}]
        res = self.update_with_values(changes)
        self.assertEqual('deactivated', res['status'])

        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'deactivated'}]
        res = self.update_with_values(changes)
        self.assertEqual('deactivated', res['status'])

        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        res = self.update_with_values(changes)
        self.assertEqual('active', res['status'])

        changes = [{'op': 'replace', 'path': '/status',
                    'value': None}]
        self.update_with_values(changes, exc_class=exc.BadRequest)

    def test_update_artifact_mutable_fields(self):
        changes = [{'op': 'replace', 'path': '/string_required',
                    'value': 'some_string'}]
        res = self.update_with_values(changes)
        self.assertEqual('some_string', res['string_required'])

        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        res = self.update_with_values(changes)
        self.assertEqual('active', res['status'])

        changes = [{'op': 'replace', 'path': '/name', 'value': 'new_name'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/metadata', 'value': {'k': 'v'}}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'add', 'path': '/metadata/k', 'value': 'v'}]
        self.update_with_values(changes, exc_class=exc.Forbidden)

        changes = [{'op': 'replace', 'path': '/tags', 'value': ['a']}]
        res = self.update_with_values(changes)
        self.assertEqual(['a'], res['tags'])

        changes = [{'op': 'add', 'path': '/tags/-', 'value': 'b'}]
        res = self.update_with_values(changes)
        self.assertEqual({'a', 'b'}, set(res['tags']))

        changes = [{'op': 'replace', 'path': '/description', 'value': 'Test'}]
        res = self.update_with_values(changes)
        self.assertEqual('Test', res['description'])

        changes = [{'op': 'replace', 'path': '/string_mutable',
                    'value': 'some_value'}]
        res = self.update_with_values(changes)
        self.assertEqual('some_value', res['string_mutable'])

    def test_update_artifact_unicode(self):
        name = u'\u0442\u0435\u0441\u0442'
        description = u'\u041E\u043F\u0438\u0441\u0430\u043D\u0438\u0435'
        tags = [u'\u041C\u0435\u0442\u043A\u0430']
        metadata = {'key': u'\u0417\u043D\u0430\u0447\u0435\u043D\u0438\u0435'}
        changes = [
            {'op': 'replace', 'path': '/name', 'value': name},
            {'op': 'replace', 'path': '/version', 'value': '1.0.0'},
            {'op': 'replace', 'path': '/description', 'value': description},
            {'op': 'replace', 'path': '/tags', 'value': tags},
            {'op': 'replace', 'path': '/metadata', 'value': metadata},
        ]
        res = self.update_with_values(changes)

        self.assertEqual(name, res['name'])
        self.assertEqual('1.0.0', res['version'])
        self.assertEqual(self.users['user1']['tenant_id'], res['owner'])
        self.assertEqual('drafted', res['status'])
        self.assertEqual('private', res['visibility'])
        self.assertEqual(description, res['description'])
        self.assertEqual(metadata, res['metadata'])
        self.assertEqual(tags, res['tags'])

    def test_update_artifact_4_byte_unicode(self):
        bad_name = u'A name with forbidden symbol \U0001f62a'
        changes = [
            {'op': 'replace', 'path': '/name', 'value': bad_name}
        ]

        self.assertRaises(exc.BadRequest, self.update_with_values, changes)
