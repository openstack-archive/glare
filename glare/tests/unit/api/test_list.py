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
from glare.tests import sample_artifact
from glare.tests.unit import base

import random


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
        res = self.controller.list(self.req, 'sample_artifact')
        self.assertEqual(7, len(res['artifacts']))
        self.assertEqual('sample_artifact', res['type_name'])
        self.assertEqual(7, res['total_count'])

        # List all artifacts as an anonymous. Only public artifacts are visible
        anon_req = self.get_fake_request(user=self.users['anonymous'])
        res = self.controller.list(anon_req, 'sample_artifact')
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(arts[4], res['artifacts'])

        # Filter by name
        filters = [('name', 'art1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))

        filters = [('name', 'in:art2,art3')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (5, 6):
            self.assertIn(arts[i], res['artifacts'])

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

        filters = [('int1', 'in:5,6')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 1, 2, 4):
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
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by created_at with eq operator leads to BadRequest
        filters = [('created_at', arts[4]['created_at'])]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by updated_at with eq operator leads to BadRequest
        filters = [('updated_at', arts[4]['updated_at'])]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by activated_at with eq operator leads to BadRequest
        filters = [('activated_at', arts[4]['activated_at'])]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by any blob leads to BadRequest
        filters = [('blob', 'something')]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by nonexistent field leads to BadRequest
        filters = [('NONEXISTENT', 'something')]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by or operation
        filters = [('float1', 'or:5.0'), ('bool1', 'or:yes')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(6, len(res['artifacts']))
        for i in (0, 1, 2, 3, 4, 6):
            self.assertIn(arts[i], res['artifacts'])

    def test_list_marker_and_limit(self):
        # Create artifacts
        art_list = [
            self.controller.create(
                self.req, 'sample_artifact',
                {'name': 'name%s' % i,
                 'version': '%d.0' % i,
                 'tags': ['tag%s' % i],
                 'int1': 1024 + i,
                 'float1': 123.456,
                 'str1': 'bugaga',
                 'bool1': True})
            for i in range(5)]

        # sort with 'next_marker'
        sort = [('int1', 'asc'), ('name', 'desc')]
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      limit=1, sort=sort)
        self.assertEqual([art_list[0]], result['artifacts'])
        marker = result['next_marker']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, limit=1, sort=sort)
        self.assertEqual([art_list[1]], result['artifacts'])
        self.assertEqual(5, result['total_count'])

        # sort by custom marker
        sort = [('int1', 'asc')]
        marker = art_list[1]['id']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, sort=sort)
        self.assertEqual(art_list[2:], result['artifacts'])

        sort = [('int1', 'desc')]
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, sort=sort)
        self.assertEqual(art_list[:1], result['artifacts'])

        sort = [('float1', 'asc'), ('name', 'desc')]
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, sort=sort)
        self.assertEqual([art_list[0]], result['artifacts'])

        # paginate by name in desc order with limit 2
        sort = [('name', 'desc')]
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      limit=2, sort=sort)
        self.assertEqual(art_list[4:2:-1], result['artifacts'])
        self.assertEqual(5, result['total_count'])

        marker = result['next_marker']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, limit=2, sort=sort)
        self.assertEqual(art_list[2:0:-1], result['artifacts'])
        self.assertEqual(5, result['total_count'])

        marker = result['next_marker']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, limit=2, sort=sort)
        self.assertEqual([art_list[0]], result['artifacts'])

        # paginate by version in desc order with limit 2
        sort = [('version', 'desc')]
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      limit=2, sort=sort)
        self.assertEqual(art_list[4:2:-1], result['artifacts'])

        marker = result['next_marker']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, limit=2, sort=sort)
        self.assertEqual(art_list[2:0:-1], result['artifacts'])

        marker = result['next_marker']
        result = self.controller.list(self.req, 'sample_artifact', filters=(),
                                      marker=marker, limit=2, sort=sort)
        self.assertEqual([art_list[0]], result['artifacts'])

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
        self.assertRaises(exc.BadRequest, self.controller.list,
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
        self.assertRaises(exc.BadRequest, self.controller.list,
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
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Filter by nonexistent dict leads to BadRequest
        filters = [('NOTEXIST.one', 'eq:1')]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        # Test with TypeError
        filters = [('dict_of_int.1', 'lala')]
        self.assertRaises(exc.BadRequest, self.controller.list,
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
        # filters = [('list_of_str', 'invalid:aa')]
        # self.assertRaises(exc.BadRequest, self.controller.list,
        #                   self.req, 'sample_artifact', filters)

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

    def test_filter_by_tags(self):
        values = [
            {'name': 'name1', 'tags': ['tag1', 'tag2']},
            {'name': 'name2', 'tags': ['tag1', 'tag3']},
            {'name': 'name3', 'tags': ['tag1']},
            {'name': 'name4', 'tags': ['tag2']},
            {'name': 'name5', 'tags': ['tag4']},
            {'name': 'name6', 'tags': ['tag4', 'tag5']},
            {'name': 'name7'},
        ]
        arts = [self.controller.create(self.req, 'sample_artifact', val)
                for val in values]

        filters = [('tags', 'tag1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 1, 2):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('tags', 'tag1,tag2')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(arts[0], res['artifacts'])

        filters = [('tags', 'NOT_A_TAG')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(0, len(res['artifacts']))

        filters = [('tags-any', 'tag1')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 1, 2):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('tags-any', 'tag1,NOT_A_TAG')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 1, 2):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('tags-any', 'tag2,tag5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (0, 3, 5):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'in:name4,name1'), ('tags-any', 'and:tag2,tag4')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (3, 0):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'or:in:name2,name1'), ('tags-any', 'or:tag2,tag5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (5, 3, 1, 0):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'or:in:name4,name1'), ('tags', 'or:tag1,tag3')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (3, 1, 0):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'or:like:name%'), ('tags-any', 'or:tag_nox_exist')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(7, len(res['artifacts']))

        # Filtering by tags with operators leads to BadRequest
        for f in ('tags', 'tags-any'):
            filters = [(f, 'eq:tag1')]
            self.assertRaises(
                exc.BadRequest, self.controller.list,
                self.req, 'sample_artifact', filters)

    def test_list_tags_base_and_additional_properties_with_sort(self):
        values = [
            {'name': 'name1', 'int1': 12, 'float1': 12.35,
             'str1': 'string_value', 'tags': ['tag1', 'tag2']},
            {'name': 'name2', 'int1': 15, 'float1': 14.38, 'str1': 'new_value',
             'list_of_str': ['str1', 'str2'], 'tags': ['tag1', 'tag3']},
            {'name': 'name3', 'int1': 15, 'float1': 14.38, 'str1': 'new_value',
             'list_of_str': ['str11', 'str2'], 'tags': ['tag1'],
             'dict_of_str': {'key1': 'value1', 'key2': 'value2'}},
            {'name': 'name4', 'int1': 15, 'float1': 14.38, 'tags': ['tag2']},
            {'name': 'name5', 'list_of_str': ['str1', 'str2'],
             'tags': ['tag4']},
            {'name': 'name6', 'tags': ['tag4', 'tag5']},
            {'name': 'name7', 'list_of_str': ['str21', 'str12']},
            {'name': 'name8', 'int1': 12,
             'dict_of_str': {'key11': 'value1', 'key12': 'value2'}},
            {'name': 'name9'}
        ]
        arts = [self.controller.create(self.req, 'sample_artifact', val)
                for val in values]

        filters = [('name', 'or:like:name%'), ('tags-any', 'or:tag_nox_exist')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(9, len(res['artifacts']))

        filters = [('name', 'or:in:name1,name9'), ('tags-any', 'or:tag2,tag4')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(5, len(res['artifacts']))
        for i in (0, 3, 4, 5, 8):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'or:in:name1,name5,name9'), ('int1', 'or:lte:13')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(4, len(res['artifacts']))
        for i in (0, 4, 7, 8):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('list_of_str', 'or:in:str11'),
                   ('tags-any', 'or:tag4,tag5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (2, 4, 5):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('list_of_str', 'or:in:str11'), ('tags', 'or:tag4,tag5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        for i in (2, 5):
            self.assertIn(arts[i], res['artifacts'])

        filters = [('name', 'or:name7'), ('dict_of_str', 'or:in:key1'),
                   ('tags', 'or:tag4,tag5')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        for i in (2, 5, 6):
            self.assertIn(arts[i], res['artifacts'])

    def test_list_and_sort_fields(self):
        amount = 7
        # Create a bunch of artifacts for list sorting tests
        names = random.sample(["art%d" % i for i in range(amount)], amount)
        floats = random.sample([0.01 * i for i in range(amount)], amount)
        ints = random.sample([1 * i for i in range(amount)], amount)
        strings = random.sample(["str%d" % i for i in range(amount)], amount)
        versions = random.sample(["0.%d" % i for i in range(amount)], amount)
        for i in range(amount):
            val = {'name': names[i], 'float1': floats[i], 'int1': ints[i],
                   'str1': strings[i], 'version': versions[i]}
            self.controller.create(self.req, 'sample_artifact', val)

        fields = ['name', 'id', 'visibility', 'version', 'float1', 'int1',
                  'str1']

        for sort_name in fields:
            for sort_dir in ['asc', 'desc']:
                arts = self.controller.list(
                    self.req, 'sample_artifact', [],
                    sort=[(sort_name, sort_dir)])['artifacts']
                self.assertEqual(amount, len(arts))
                sorted_arts = sorted(arts, key=lambda x: x[sort_name],
                                     reverse=sort_dir == 'desc')
                self.assertEqual(sorted_arts, arts)

    def test_list_and_sort_negative(self):
        # sort by non-existent field
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact',
                          [], sort=[("NONEXISTENT", "desc")])

        # sort by wrong direction
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact',
                          [], sort=[("name", "WRONG_DIR")])

        # For performance sake sorting by more than one custom field
        # is forbidden. Nevertheless, sorting by several basic field are
        # absolutely fine.
        # List of basic fields is located in glare/db/sqlalchemy/api.py as
        # BASE_ARTIFACT_PROPERTIES tuple.
        sort = [("int1", "desc"), ("float1", "desc")]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact',
                          [], sort=sort)

        # sort with non-sortable fields
        for name, field in sample_artifact.SampleArtifact.fields.items():
            for sort_dir in ['asc', 'desc']:
                if not field.sortable:
                    self.assertRaises(
                        exc.BadRequest, self.controller.list,
                        self.req, 'sample_artifact',
                        [], sort=[(name, sort_dir)])

    def test_list_like_filter(self):
        val = {'name': '0', 'str1': 'banana'}
        art0 = self.controller.create(self.req, 'sample_artifact', val)
        val = {'name': '1', 'str1': 'nan'}
        art1 = self.controller.create(self.req, 'sample_artifact', val)
        val = {'name': '2', 'str1': 'anab'}
        self.controller.create(self.req, 'sample_artifact', val)

        filters = [('str1', 'like:%banana%')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(1, len(res['artifacts']))
        self.assertIn(art0, res['artifacts'])

        filters = [('str1', 'like:%nan%')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        self.assertIn(art0, res['artifacts'])
        self.assertIn(art1, res['artifacts'])

        filters = [('str1', 'like:%na%')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))

        filters = [('str1', 'like:%haha%')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(0, len(res['artifacts']))

    def test_list_query_combiner(self):
        values = [{'name': 'combiner0', 'str1': 'banana'},
                  {'name': 'combiner1', 'str1': 'nan'},
                  {'name': 'combiner2', 'str1': 'anab'},
                  {'name': 'combiner3', 'str1': 'blabla'}]

        [self.controller.create(self.req, 'sample_artifact', val)
         for val in values]

        filters = [('str1', 'or:nan'), ('name', 'or:combiner3')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(2, len(res['artifacts']))
        self.assertEqual(2, res['total_count'])

        filters = [('str1', 'or:like:%nan%'), ('str1', 'or:blabla')]
        res = self.controller.list(self.req, 'sample_artifact', filters)
        self.assertEqual(3, len(res['artifacts']))
        self.assertEqual(3, res['total_count'])

        filters = [('name', 'or:tt:ttt'), ('str1', "or:blabla")]
        self.assertRaises(exc.BadRequest, self.controller.list,
                          self.req, 'sample_artifact', filters)

        res = self.controller.create(self.req, 'heat_templates',
                                     {'name': "artifact_without_properties"})

        filters = [('name', 'or:eq:non_existant_name'),
                   ('id', 'or:eq:' + res['id'])]
        res = self.controller.list(self.req, 'heat_templates',
                                   filters)['artifacts']
        self.assertEqual(1, len(res))
        self.assertEqual('artifact_without_properties', res[0]['name'])
