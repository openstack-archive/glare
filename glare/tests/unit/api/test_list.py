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


class TestArtifactList(base.BaseTestArtifactAPI):

    def test_list_simple_fields(self):
        # Create a bunch of artifacts for list testing
        values = [
            {'name': 'art1', 'version': '0.0.1', 'string_required': 'str1',
             'int1': 5, 'float1': 5.0, 'bool1': 'yes'},
            {'name': 'art1', 'version': '1-beta', 'string_required': 'str2',
             'int1': 6, 'float1': 6.0, 'bool1': 'yes'},
            {'name': 'art1', 'version': '1', 'string_required': 'str1',
             'int1': 5, 'float1': 5.0, 'bool1': 'no', 'description': 'ggg'},
            {'name': 'art1', 'version': '2-rc1', 'string_required': 'str22',
             'int1': 7, 'float1': 7.0, 'bool1': 'yes'},
            {'name': 'art1', 'version': '10', 'string_required': 'str222',
             'int1': 5, 'float1': 5.0, 'bool1': 'yes'},
            {'name': 'art2', 'version': '1', 'string_required': 'str1',
             'int1': 8, 'float1': 8.0, 'bool1': 'no'},
            {'name': 'art3', 'version': '1', 'string_required': 'str1',
             'int1': -5, 'float1': -5.0, 'bool1': 'yes'},
        ]
        arts = [self.controller.create(self.req, 'sample_artifact', val)
                for val in values]

        # Activate 3rd and 4th artifacts
        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        arts[3] = self.update_with_values(changes, art_id=arts[3]['id'])
        arts[4] = self.update_with_values(changes, art_id=arts[4]['id'])

        # Publish 4th artifact
        changes = [{'op': 'replace', 'path': '/visibility', 'value': 'public'}]
        self.req = self.get_fake_request(user=self.users['admin'])
        arts[4] = self.update_with_values(changes, art_id=arts[4]['id'])
        self.req = self.get_fake_request(user=self.users['user1'])

        # Do tests basic tests
        # input format for filters is a list of tuples:
        # (filter_name, filter_value)

        # List all artifacts
        res = self.controller.list(self.req, 'sample_artifact', [])
        self.assertEqual(7, len(res['artifacts']))
        self.assertEqual('sample_artifact', res['type_name'])

        # Filter by name
        filters = [('name', 'art1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))

        # Filter by string_required
        filters = [('string_required', 'str1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 2, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by int1
        filters = [('int1', '5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 4):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by float1
        filters = [('float1', '5.0')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 4):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by bool1
        filters = [('bool1', 'yes')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))
        for i in (0, 1, 3, 4, 6):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by id
        filters = [('id', arts[0]['id'])]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(arts[0], res['artifacts'])

        # Filter by status
        filters = [('status', 'active')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (3, 4):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by visibility
        filters = [('visibility', 'public')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(arts[4], res['artifacts'])

        # Filter by owner
        filters = [('owner', arts[0]['owner'])]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(7, len(res['artifacts']))
        for i in range(6):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by description leads to BadRequest
        filters = [('description', 'ggg')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Filter by created_at with eq operator leads to BadRequest
        filters = [('created_at', arts[4]['created_at'])]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Filter by updated_at with eq operator leads to BadRequest
        filters = [('updated_at', arts[4]['updated_at'])]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Filter by activated_at with eq operator leads to BadRequest
        filters = [('activated_at', arts[4]['activated_at'])]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Filter by any blob leads to BadRequest
        filters = [('blob', 'something')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

    def test_list_version(self):
        values = [
            {'name': 'art1', 'version': '0.0.1'},
            {'name': 'art1', 'version': '1-beta'},
            {'name': 'art1', 'version': '1'},
            {'name': 'art1', 'version': '10-rc1'},
            {'name': 'art1', 'version': '10'},
            {'name': 'art2', 'version': '1'},
            {'name': 'art3', 'version': '1'},
        ]

        arts = [self.controller.create(self.req, 'sample_artifact', val)
                for val in values]

        # List all artifacts
        res = self.controller.list(self.req, 'sample_artifact', [])
        self.assertEqual(7, len(res['artifacts']))
        self.assertEqual('sample_artifact', res['type_name'])

        # Get latest artifacts
        res = self.controller.list(self.req, 'sample_artifact', [],
                                   latest=True)
        self.assertEqual(3, len(res['artifacts']))
        for i in (4, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        # Various version filters
        filters = [('version', '1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (2, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('version', '1'), ('name', 'art1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(arts[2], res['artifacts'])

        filters = [('version', 'gt:1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (3, 4):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('version', 'gte:1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))
        for i in (2, 3, 4, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('version', 'lte:1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))
        for i in (0, 1, 2, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('version', 'gt:1-beta'), ('version', 'lt:10')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (2, 3, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('version', 'in:0.0.1,10-rc1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (0, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by invalid version
        filters = [('version', 'INVALID_VERSION')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Filter by invalid operator
        filters = [('version', 'INVALID_op:1')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

    def test_list_compound_fields(self):
        # Create a bunch of artifacts for list testing
        values = [
            {'name': 'art1',
             'dict_of_str': {'a': 'aa', 'b': 'bb'},
             'dict_of_int': {'one': 1, 'two': 2},
             'list_of_str': ['aa', 'bb'],
             'list_of_int': [1, 2]},
            {'name': 'art2',
             'dict_of_str': {'b': 'bb', 'c': 'cc'},
             'dict_of_int': {'two': 2, 'three': 3},
             'list_of_str': ['bb', 'cc'],
             'list_of_int': [2, 3]},
            {'name': 'art3',
             'dict_of_str': {'a': 'aa', 'c': 'cc'},
             'dict_of_int': {'one': 1, 'three': 3},
             'list_of_str': ['aa', 'cc'],
             'list_of_int': [1, 3]},
            {'name': 'art4',
             'dict_of_str': {'a': 'bb'},
             'dict_of_int': {'one': 2},
             'list_of_str': ['aa'],
             'list_of_int': [1]},
            {'name': 'art5',
             'dict_of_str': {'b': 'bb'},
             'dict_of_int': {'two': 2},
             'list_of_str': ['bb'],
             'list_of_int': [2]},
            {'name': 'art6',
             'dict_of_str': {},
             'dict_of_int': {},
             'list_of_str': [],
             'list_of_int': []},
        ]
        arts = [self.controller.create(self.req, 'sample_artifact', val)
                for val in values]

        # List all artifacts
        res = self.controller.list(self.req, 'sample_artifact', [])
        self.assertEqual(6, len(res['artifacts']))
        self.assertEqual('sample_artifact', res['type_name'])

        # Return artifacts that contain key 'a' in 'dict_of_str'
        filters = [('dict_of_str', 'eq:a')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain key 'a' or 'c' in 'dict_of_str'
        filters = [('dict_of_str', 'in:a,c')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 1, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter with invalid operator leads to BadRequest
        filters = [('dict_of_str', 'invalid:a')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Return artifacts that contain key one in 'dict_of_int'
        filters = [('dict_of_int', 'eq:one')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain key one or three in 'dict_of_int'
        filters = [('dict_of_int', 'in:one,three')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 1, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter by dicts values
        # Return artifacts that contain value 'bb' in 'dict_of_str[b]'
        filters = [('dict_of_str.b', 'eq:bb')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 1, 4):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain values 'aa' or 'bb' in 'dict_of_str[a]'
        filters = [('dict_of_str.a', 'in:aa,bb')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter with invalid operator leads to BadRequest
        filters = [('dict_of_str.a', 'invalid:aa')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Return artifacts that contain value '2' in 'dict_of_int[two]'
        filters = [('dict_of_int.two', 'eq:2')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 1, 4):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain values '1' or '2' in 'dict_of_int[one]'
        filters = [('dict_of_int.one', 'in:1,2')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter with invalid operator leads to BadRequest
        filters = [('dict_of_int.one', 'invalid:1')]
        self. assertRaises(exc.BadRequest, self.controller.list,
                           self.req, 'sample_artifact', filters)

        # Return artifacts that contain key 'aa' in 'list_of_str'
        filters = [('list_of_str', 'eq:aa')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain key 'aa' or 'cc' in 'list_of_str'
        filters = [('list_of_str', 'in:aa,cc')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 1, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Filter with invalid operator leads to BadRequest
        filters = [('list_of_str', 'invalid:aa')]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Return artifacts that contain key 1 in 'list_of_int'
        filters = [('list_of_int', 'eq:1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 2, 3):
            self.assertIn(arts[i], res['artifacts'])

        # Return artifacts that contain key 1 or three in 'list_of_int'
        filters = [('list_of_int', 'in:1,3')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 1, 2, 3):
            self.assertIn(arts[i], res['artifacts'])
