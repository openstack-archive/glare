# Copyright 2016 OpenStack Foundation
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

import hashlib
import uuid

from oslo_serialization import jsonutils
import requests

from glare.tests.functional import base


def sort_results(lst, target='name'):
    return sorted(lst, key=lambda x: x[target])


class TestList(base.TestArtifact):
    def test_list_marker_and_limit(self):
        # Create artifacts
        art_list = [self.create_artifact({'name': 'name%s' % i,
                                          'version': '1.0',
                                          'tags': ['tag%s' % i],
                                          'int1': 1024 + i,
                                          'float1': 123.456,
                                          'str1': 'bugaga',
                                          'bool1': True})
                    for i in range(5)]

        # sort by 'next' url
        url = '/sample_artifact?limit=1&sort=int1:asc,name:desc'
        result = self.get(url=url)
        self.assertEqual([art_list[0]], result['artifacts'])
        marker = result['next']
        result = self.get(url=marker[10:])
        self.assertEqual([art_list[1]], result['artifacts'])
        self.assertEqual(5, result['total_count'])

        # sort by custom marker
        url = '/sample_artifact?sort=int1:asc&marker=%s' % art_list[1]['id']
        result = self.get(url=url)
        self.assertEqual(art_list[2:], result['artifacts'])
        url = '/sample_artifact?sort=int1:desc&marker=%s' % art_list[1]['id']
        result = self.get(url=url)
        self.assertEqual(art_list[:1], result['artifacts'])
        url = '/sample_artifact' \
              '?sort=float1:asc,name:desc&marker=%s' % art_list[1]['id']
        result = self.get(url=url)
        self.assertEqual([art_list[0]], result['artifacts'])

        # paginate by name in desc order with limit 2
        url = '/sample_artifact?limit=2&sort=name:desc'
        result = self.get(url=url)
        self.assertEqual(art_list[4:2:-1], result['artifacts'])
        marker = result['next']
        result = self.get(url=marker[10:])
        self.assertEqual(art_list[2:0:-1], result['artifacts'])
        marker = result['next']
        result = self.get(url=marker[10:])
        self.assertEqual([art_list[0]], result['artifacts'])
        self.assertEqual(5, result['total_count'])

    def test_list_base_filters(self):
        # Create artifact
        art_list = [self.create_artifact({'name': 'name%s' % i,
                                          'version': '1.0',
                                          'tags': ['tag%s' % i],
                                          'int1': 1024,
                                          'float1': 123.456,
                                          'str1': 'bugaga',
                                          'bool1': True})
                    for i in range(5)]

        public_art = self.create_artifact({'name': 'name5',
                                           'version': '1.0',
                                           'tags': ['tag4', 'tag5'],
                                           'int1': 2048,
                                           'float1': 987.654,
                                           'str1': 'lalala',
                                           'bool1': False,
                                           'string_required': '123'})
        url = '/sample_artifact/%s' % public_art['id']
        data = [{
            "op": "replace",
            "path": "/status",
            "value": "active"
        }]
        self.patch(url=url, data=data, status=200)
        public_art = self.admin_action(public_art['id'], self.make_public)

        art_list.append(public_art)

        art_list.sort(key=lambda x: x['name'])

        url = '/sample_artifact?str1=bla:empty'
        self.get(url=url, status=400)

        url = '/sample_artifact?str1=bla:empty'
        self.get(url=url, status=400)

        url = '/sample_artifact?name=name0'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([art_list[0]], result)

        url = '/sample_artifact?tags=tag4'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[4:], result)

        url = '/sample_artifact?name=eq:name0'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:1], result)

        url = '/sample_artifact?str1=eq:bugaga'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?int1=eq:2048'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?float1=eq:123.456'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?name=neq:name0'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[1:], result)

        url = '/sample_artifact?name=in:name,name0'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:1], result)

        url = '/sample_artifact?name=in:not_exist,name0'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:1], result)

        url = '/sample_artifact?name=not_exist'
        result = self.get(url=url)['artifacts']
        self.assertEqual([], result)

        url = '/sample_artifact?name=bla:name1'
        self.get(url=url, status=400)

        url = '/sample_artifact?name='
        self.get(url=url, status=400)

        url = '/sample_artifact?name=eq:'
        self.get(url=url, status=400)

        url = '/sample_artifact?tags=tag4,tag5'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?tags-any=tag4'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[4:], result)

        url = '/sample_artifact?tags=tag4,tag_not_exist,tag5'
        result = self.get(url=url)['artifacts']
        self.assertEqual([], result)

        url = '/sample_artifact?tags-any=tag4,tag_not_exist,tag5'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[4:], result)

        url = '/sample_artifact?tags=tag_not_exist,tag_not_exist_1'
        result = self.get(url=url)['artifacts']
        self.assertEqual([], result)

        url = '/sample_artifact?tags'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list, result)

        url = '/sample_artifact?tags='
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list, result)

        url = '/sample_artifact?tags=eq:tag0'
        self.get(url=url, status=400)

        url = '/sample_artifact?tags=bla:tag0'
        self.get(url=url, status=400)

        url = '/sample_artifact?tags=neq:tag1'
        self.get(url=url, status=400)

        url = '/sample_artifact?visibility=private'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?visibility=public'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?visibility=eq:private'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?visibility=eq:public'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?visibility=neq:private'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?visibility=neq:public'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?visibility=blabla'
        self.get(url=url, status=400)

        url = '/sample_artifact?visibility=neq:blabla'
        self.get(url=url, status=400)

        url = '/sample_artifact?name=eq:name0&name=name1&tags=tag1'
        result = self.get(url=url)['artifacts']
        self.assertEqual([], result)

        url = '/sample_artifact?int1=gt:2000'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?int1=lte:1024'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?int1=gt:1000&int1=lt:2000'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?int1=lt:2000'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?float1=gt:200.000'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?float1=gt:100.00&float1=lt:200.00'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?float1=lt:200.00'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?float1=lt:200'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?float1=lte:123.456'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?bool1=True'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?bool1=False'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        url = '/sample_artifact?bool1=False'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[5:], result)

        # Like filter test cases for name, status
        url = '/sample_artifact?name=like:name%'
        artifacts = self.get(url=url)['artifacts']
        for artifact in artifacts:
            self.assertEqual("name", artifact.get("name")[:4])

    def test_artifact_list_dict_filters(self):
        lists_of_str = [
            ['aaa', 'bbb', 'ccc'],
            ['aaa', 'bbb'],
            ['aaa', 'ddd'],
            ['bbb'],
            ['ccc']
        ]
        dicts_of_str = [
            {'aaa': 'z', 'bbb': 'z', 'ccc': 'z'},
            {'aaa': 'z', 'bbb': 'z'},
            {'aaa': 'z', 'ddd': 'z'},
            {'bbb': 'z'},
            {'ccc': 'z'}
        ]
        art_list = [self.create_artifact({'name': 'name%s' % i,
                                          'version': '1.0',
                                          'tags': ['tag%s' % i],
                                          'int1': 1024,
                                          'float1': 123.456,
                                          'str1': 'bugaga',
                                          'bool1': True,
                                          'list_of_str': lists_of_str[i],
                                          'dict_of_str': dicts_of_str[i]})
                    for i in range(5)]

        # test list filters
        url = '/sample_artifact?list_of_str=aaa&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:3], result)

        url = '/sample_artifact?list_of_str=ccc&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([art_list[0], art_list[4]], result)

        url = '/sample_artifact?list_of_str=eee&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        # test dict filters
        url = '/sample_artifact?dict_of_str=aaa&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:3], result)

        url = '/sample_artifact?dict_of_str=ccc&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([art_list[0], art_list[4]], result)

        url = '/sample_artifact?dict_of_str=eee&sort=name'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

    def test_list_dict_prop_filters(self):
        # Create artifact
        art_list = [self.create_artifact({'name': 'name0',
                                          'version': '1.0',
                                          'dict_of_str': {'pr1': 'val1'}}),
                    self.create_artifact({'name': 'name1',
                                          'version': '1.0',
                                          'dict_of_str': {'pr1': 'val1',
                                                          'pr2': 'val2'}}),
                    self.create_artifact({'name': 'name2',
                                          'version': '1.0',
                                          'dict_of_str': {'pr3': 'val3'}}),
                    self.create_artifact({'name': 'name3',
                                          'version': '1.0',
                                          'dict_of_str': {'pr3': 'val1'},
                                          'dict_of_int': {"1": 10, "2": 20}}),
                    self.create_artifact({'name': 'name4',
                                          'version': '1.0',
                                          'dict_of_str': {},
                                          'dict_of_int': {"2": 20, "3": 30}}),
                    ]

        art_list.sort(key=lambda x: x['name'])

        url = '/sample_artifact?dict_of_str.pr1=val1'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:2], result)

        url = '/sample_artifact?dict_of_int.1=10'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[3:4], result)

        url = '/sample_artifact?dict_of_str.pr1=val999'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        url = '/sample_artifact?dict_of_str.pr1=eq:val1'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:2], result)

        url = '/sample_artifact?dict_of_str.'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        for op in ['gt', 'gte', 'lt', 'lte']:
            url = '/sample_artifact?dict_of_str.pr3=%s:val3' % op
            self.get(url=url, status=400)

        url = '/sample_artifact?dict_of_str.pr3=blabla:val3'
        self.get(url=url, status=400)

        url = '/sample_artifact?dict_of_str.pr1='
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        url = '/sample_artifact?dict_of_str.pr1='
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        url = '/sample_artifact?dict_of_str'
        self.assertEqual([], result)

        url = '/sample_artifact?dict_of_str.pr3=blabla:val3'
        self.get(url=url, status=400)

        url = '/sample_artifact?list_of_str.pr3=blabla:val3'
        self.get(url=url, status=400)

        url = '/sample_artifact?dict_of_str.bla=val1'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual([], result)

        url = '/sample_artifact?dict_of_int.1=lala'
        self.get(url=url, status=400)

    def test_list_sorted(self):
        art_list = [self.create_artifact({'name': 'name%s' % i,
                                          'version': '1.0',
                                          'tags': ['tag%s' % i],
                                          'int1': i,
                                          'float1': 123.456 + (-0.9) ** i,
                                          'str1': 'bugaga',
                                          'bool1': True,
                                          'list_of_int': [11, 22, - i],
                                          'dict_of_int': {'one': 4 * i,
                                                          'two': (-2) ** i}})
                    for i in range(5)]

        # sorted by string 'asc'
        url = '/sample_artifact?sort=name:asc'
        result = self.get(url=url)
        expected = sort_results(art_list)
        self.assertEqual(expected, result['artifacts'])

        # sorted by string 'desc'
        url = '/sample_artifact?sort=name:desc'
        result = self.get(url=url)
        expected = sort_results(art_list)
        expected.reverse()
        self.assertEqual(expected, result['artifacts'])

        # sorted by int 'asc'
        url = '/sample_artifact?sort=int1:asc'
        result = self.get(url=url)
        expected = sort_results(art_list, target='int1')
        self.assertEqual(expected, result['artifacts'])

        # sorted by int 'desc'
        url = '/sample_artifact?sort=int1:desc'
        result = self.get(url=url)
        expected = sort_results(art_list, target='int1')
        expected.reverse()
        self.assertEqual(expected, result['artifacts'])

        # sorted by float 'asc'
        url = '/sample_artifact?sort=float1:asc'
        result = self.get(url=url)
        expected = sort_results(art_list, target='float1')
        self.assertEqual(expected, result['artifacts'])

        # sorted by float 'desc'
        url = '/sample_artifact?sort=float1:desc'
        result = self.get(url=url)
        expected = sort_results(art_list, target='float1')
        expected.reverse()
        self.assertEqual(expected, result['artifacts'])

        # sorted by unsorted 'asc'
        url = '/sample_artifact?sort=bool1:asc'
        self.get(url=url, status=400)

        # sorted by unsorted 'desc'
        url = '/sample_artifact?sort=bool1:desc'
        self.get(url=url, status=400)

        # sorted by non-existent 'asc'
        url = '/sample_artifact?sort=non_existent:asc'
        self.get(url=url, status=400)

        # sorted by non-existent 'desc'
        url = '/sample_artifact?sort=non_existent:desc'
        self.get(url=url, status=400)

        # sorted by invalid op
        url = '/sample_artifact?sort=name:invalid_op'
        self.get(url=url, status=400)

        # sorted without op
        url = '/sample_artifact?sort=name'
        result = self.get(url=url)
        expected = sort_results(art_list)
        expected.reverse()
        self.assertEqual(expected, result['artifacts'])

        # sorted by list
        url = '/sample_artifact?sort=list_of_int:asc'
        self.get(url=url, status=400)

        # sorted by dict
        url = '/sample_artifact?sort=dict_of_int:asc'
        self.get(url=url, status=400)

        # sorted by element of dict
        url = '/sample_artifact?sort=dict_of_int.one:asc'
        self.get(url=url, status=400)

        # sorted by any prop
        url = '/sample_artifact?sort=name:asc,int1:desc'
        result = self.get(url=url)
        expected = sort_results(sort_results(art_list), target='int1')
        self.assertEqual(expected, result['artifacts'])

    def test_list_versions(self):
        # Create artifacts with versions
        version_list = ['1.0', '1.1', '2.0.0', '2.0.1-beta', '2.0.1', '20.0']

        # Create artifact
        art_list = [self.create_artifact({'name': 'name',
                                          'version': version_list[i - 1],
                                          'tags': ['tag%s' % i],
                                          'int1': 2048,
                                          'float1': 123.456,
                                          'str1': 'bugaga',
                                          'bool1': True})
                    for i in range(1, 7)]

        public_art = self.create_artifact(
            {'name': 'name',
             'tags': ['tag4', 'tag5'],
             'int1': 1024,
             'float1': 987.654,
             'str1': 'lalala',
             'bool1': False,
             'string_required': '123'})
        url = '/sample_artifact/%s' % public_art['id']
        data = [{
            "op": "replace",
            "path": "/status",
            "value": "active"
        }]
        self.patch(url=url, data=data, status=200)
        public_art = self.admin_action(public_art['id'], self.make_public)

        art_list.insert(0, public_art)

        expected_result = sort_results(art_list, target='version')
        url = '/sample_artifact'
        result = sort_results(self.get(url=url)['artifacts'],
                              target='version')
        self.assertEqual(expected_result, result)

        # Creating an artifact with existing version fails
        self.create_artifact(
            {'name': 'name',
             'version': '1.0',
             'tags': ['tag1'],
             'int1': 2048,
             'float1': 123.456,
             'str1': 'bugaga',
             'bool1': True},
            status=409)

        url = '/sample_artifact?name=name&version=gte:2.0.0'
        result = sort_results(self.get(url=url)['artifacts'],
                              target='version')
        self.assertEqual(expected_result[3:], result)

        url = ('/sample_artifact?'
               'name=name&version=gte:1.1&version=lt:2.0.1-beta')
        result = sort_results(self.get(url=url)['artifacts'],
                              target='version')
        self.assertEqual(expected_result[2:4], result)

        # Filtering by version without name is ok
        url = '/sample_artifact?version=gte:2.0.0'
        self.get(url=url, status=200)

        # Several name filters with version is ok
        url = '/sample_artifact?name=name&name=anothername&version=gte:2.0.0'
        self.get(url=url, status=200)

        # Filtering by version with name filter op different from 'eq'
        url = '/sample_artifact?version=gte:2.0.0&name=neq:name'
        self.get(url=url, status=200)

        # Sorting by version 'asc'
        url = '/sample_artifact?name=name&sort=version:asc'
        result = self.get(url=url)['artifacts']
        self.assertEqual(art_list, result)

        # Sorting by version 'desc'
        url = '/sample_artifact?name=name&sort=version:desc'
        result = self.get(url=url)['artifacts']
        self.assertEqual(list(reversed(art_list)), result)

    def test_list_latest_filter(self):
        # Create artifacts with versions
        group1_versions = ['1.0', '20.0', '2.0.0', '2.0.1-beta', '2.0.1']
        group2_versions = ['1', '1000.0.1-beta', '99.0',
                           '1000.0.1-alpha', '1000.0.1']

        for i in range(5):
            self.create_artifact(
                {'name': 'group1',
                 'version': group1_versions[i],
                 'tags': ['tag%s' % i],
                 'int1': 2048 + i,
                 'float1': 123.456,
                 'str1': 'bugaga',
                 "string_required": "test_str",
                 'bool1': True})
            self.create_artifact(
                {'name': 'group2',
                 'version': group2_versions[i],
                 'tags': ['tag%s' % i],
                 'int1': 2048 + i,
                 'float1': 123.456,
                 'str1': 'bugaga',
                 "string_required": "test_str",
                 'bool1': True})

        url = '/sample_artifact?version=latest&sort=name:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(2, len(res))
        self.assertEqual('20.0.0', res[0]['version'])
        self.assertEqual('1000.0.1', res[1]['version'])

        self.patch('/sample_artifact/' + res[0]['id'], self.make_active)

        url = '/sample_artifact?version=latest&sort=name:asc&status=drafted'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(2, len(res))
        self.assertEqual('2.0.1', res[0]['version'])
        self.assertEqual('1000.0.1', res[1]['version'])

        url = '/sample_artifact?version=latest&sort=name:asc&int1=2050'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(2, len(res))
        self.assertEqual('2.0.0', res[0]['version'])
        self.assertEqual('99.0.0', res[1]['version'])

        url = '/sample_artifact?version=latest&name=group1'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(1, len(res))
        self.assertEqual('20.0.0', res[0]['version'])

        url = '/sample_artifact?version=latest&name=group2'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(1, len(res))
        self.assertEqual('1000.0.1', res[0]['version'])

    def test_list_support_unicode_filters(self):
        unicode_text = u'\u041f\u0420\u0418\u0412\u0415\u0422'
        art1 = self.create_artifact(data={'name': unicode_text})
        self.assertEqual(unicode_text, art1['name'])

        mixed_text = u'la\u041f'
        art2 = self.create_artifact(data={'name': mixed_text})
        self.assertEqual(mixed_text, art2['name'])

        headers = {'Content-Type': 'text/html; charset=UTF-8'}
        url = u'/sample_artifact?name=\u041f\u0420\u0418\u0412\u0415\u0422'
        response_url = u'/artifacts/sample_artifact?name=' \
                       u'%D0%9F%D0%A0%D0%98%D0%92%D0%95%D0%A2'
        result = self.get(url=url, headers=headers)
        self.assertEqual(art1, result['artifacts'][0])
        self.assertEqual(response_url, result['first'])

    def test_list_response_attributes(self):
        url = '/sample_artifact'
        res = self.get(url=url, status=200)
        self.assertEqual(res['total_count'], 0)

    def test_list_artifact_with_filter_query_combiner(self):
        # Create artifact
        art_list = [self.create_artifact({'name': 'name%s' % i,
                                          'version': '2.0',
                                          'tags': ['tag%s' % i],
                                          'int1': 1024,
                                          'float1': 123.456,
                                          'str1': 'bugaga',
                                          'bool1': True})
                    for i in range(5)]

        public_art = self.create_artifact({'name': 'name5',
                                           'version': '2.0',
                                           'tags': ['tag4', 'tag5'],
                                           'int1': 2048,
                                           'float1': 987.654,
                                           'str1': 'lalala',
                                           'bool1': False,
                                           'string_required': '123'})
        url = '/sample_artifact/%s' % public_art['id']
        data = [{
            "op": "replace",
            "path": "/status",
            "value": "active"
        }]

        self.patch(url=url, data=data, status=200)
        public_art = self.admin_action(public_art['id'], self.make_public)

        art_list.append(public_art)

        url = '/sample_artifact?float1=and:lte:123.456&str1=or:eq:lalal&' \
              'str1=or:eq:bugaga'
        result = sort_results(self.get(url=url)['artifacts'])
        self.assertEqual(art_list[:5], result)

        url = '/sample_artifact?str1=or:blah:t'
        self.get(url=url, status=400)

        url = '/sample_artifact?str1=or:blabla:t:tt'
        self.get(url=url, status=400)

        url = '/sample_artifact?str1=or:eq:blabla:t:tt'
        result = self.get(url=url)['artifacts']
        self.assertEqual([], result)

        url = '/sample_artifact?name=or:eq:name2&tags-any=or:tag1,tag4' \
              '&sort=name:asc'
        result = self.get(url=url)['artifacts']
        self.assertEqual(4, len(result))
        for i in (1, 2, 4):
            self.assertIn(art_list[i], result)
        self.assertEqual(public_art, result[3])

        url = '/sample_artifact?name=or:eq:name2&&tags=or:tag4,tag5' \
              '&sort=name:asc'
        result = self.get(url=url)['artifacts']
        self.assertEqual(2, len(result))
        self.assertEqual(art_list[2], result[0])
        self.assertEqual(public_art, result[1])

    def test_list_display_type_name_attribute(self):

        [self.create_artifact({'name': 'name%s' % i,
                               'version': '2.0',
                               'tags': ['tag%s' % i],
                               'int1': 1024,
                               'float1': 123.456,
                               'str1': 'bugaga',
                               'bool1': True})
         for i in range(5)]

        url = '/sample_artifact'
        result = self.get(url)['artifacts']
        self.assertEqual(True, len(result) > 0)
        for artifact in result:
            self.assertEqual('Sample Artifact', artifact['display_type_name'])

        # validate for show artifact API
        url = '/sample_artifact/%s' % result[0]['id']
        result = self.get(url)
        self.assertEqual('Sample Artifact', result['display_type_name'])


class TestBlobs(base.TestArtifact):
    def test_blob_dicts(self):
        # Getting empty artifact list
        url = '/sample_artifact'
        response = self.get(url=url, status=200)
        expected = {'first': '/artifacts/sample_artifact',
                    'artifacts': [],
                    'schema': '/schemas/sample_artifact',
                    'type_name': 'sample_artifact',
                    'total_count': 0}
        self.assertEqual(expected, response)

        # Create a test artifact
        art = self.create_artifact(status=201,
                                   data={'name': 'test',
                                         'version': '1.0',
                                         'string_required': '123'})
        self.assertIsNotNone(art['id'])

        # Get the artifact which should have a generated id and status
        # 'drafted'
        url = '/sample_artifact/%s' % art['id']
        art_1 = self.get(url=url, status=200)
        self.assertIsNotNone(art_1['id'])
        self.assertEqual('drafted', art_1['status'])

        # Upload data to blob dict
        headers = {'Content-Type': 'application/octet-stream'}
        data = "data" * 100
        blob_name = 'blob_name' * 100
        self.put(url=url + '/dict_of_blobs/' + blob_name,
                 data=data, status=200, headers=headers)

        # Download data from blob dict
        self.assertEqual(data,
                         self.get(url=url + '/dict_of_blobs/' + blob_name,
                                  status=200))

        # Download blob from undefined dict property
        self.get(url=url + '/not_a_dict/not_a_blob', status=400)

        # Blob url is generated right
        art = self.get(url=url, status=200)
        exp_blob_url = '/artifacts' + url + '/dict_of_blobs/' + blob_name
        self.assertEqual(exp_blob_url,
                         art['dict_of_blobs'][blob_name]['url'])

    def test_blob_upload(self):
        # create artifact with blob
        data = 'data'
        self.create_artifact(
            data={'name': 'test_af', 'blob': data,
                  'version': '0.0.1'}, status=400)
        art = self.create_artifact(data={'name': 'test_af',
                                         'version': '0.0.1',
                                         'string_required': 'test'})
        url = '/sample_artifact/%s' % art['id']
        headers = {'Content-Type': 'application/octet-stream',
                   'Content-Length': '4'}

        # upload to non-existing property
        self.put(url=url + '/blob_non_exist', data=data, status=400,
                 headers=headers)

        # upload too big value
        big_data = "this is the smallest big data"
        self.put(url=url + '/small_blob', data=big_data, status=413,
                 headers=headers)
        # upload correct blob value
        self.put(url=url + '/small_blob', data=big_data[:2], headers=headers)

        # Upload artifact via different user
        self.set_user('user2')
        self.put(url=url + '/blob', data=data, status=404,
                 headers=headers)

        # Upload file to the artifact
        self.set_user('user1')
        art = self.put(url=url + '/blob', data=data, status=200,
                       headers=headers)
        self.assertEqual('active', art['blob']['status'])
        self.assertEqual('application/octet-stream',
                         art['blob']['content_type'])
        self.assertIn('url', art['blob'])
        self.assertNotIn('id', art['blob'])

        # Blob url is generated right
        exp_blob_url = '/artifacts' + url + '/blob'
        self.assertEqual(exp_blob_url, art['blob']['url'])

        # reUpload file to artifact
        self.put(url=url + '/blob', data=data, status=200,
                 headers=headers)
        # upload blob dict
        self.put(url + '/dict_of_blobs/test_key', data=data, headers=headers)
        # test re-upload for dict of blob.
        self.put(url + '/dict_of_blobs/test_key', data=data, headers=headers,
                 status=200)

        # upload few other blobs to the dict
        for elem in ('aaa', 'bbb', 'ccc', 'ddd'):
            self.put(url + '/dict_of_blobs/' + elem, data=data,
                     headers=headers)

        # upload to active artifact
        self.patch(url, self.make_active)
        self.put(url + '/dict_of_blobs/key2', data=data, status=403,
                 headers=headers)

        self.delete(url)

    def test_blob_download(self):
        data = 'some_arbitrary_testing_data'
        art = self.create_artifact(data={'name': 'test_af',
                                         'version': '0.0.1'})
        url = '/sample_artifact/%s' % art['id']

        # download not uploaded blob
        self.get(url=url + '/blob', status=404)

        # download blob from not existing artifact
        self.get(url=url + '1/blob', status=404)

        # download blob from undefined property
        self.get(url=url + '/not_a_blob', status=400)

        headers = {'Content-Type': 'application/octet-stream'}
        art = self.put(url=url + '/blob', data=data, status=200,
                       headers=headers)
        self.assertEqual('active', art['blob']['status'])
        md5 = hashlib.md5(data.encode('UTF-8')).hexdigest()
        sha1 = hashlib.sha1(data.encode('UTF-8')).hexdigest()
        sha256 = hashlib.sha256(data.encode('UTF-8')).hexdigest()
        self.assertEqual(md5, art['blob']['md5'])
        self.assertEqual(sha1, art['blob']['sha1'])
        self.assertEqual(sha256, art['blob']['sha256'])

        # check that content-length is in response
        response = requests.get(self._url(url + '/blob'),
                                headers=self._headers())
        self.assertEqual('27', response.headers["content-length"])

        # check that all checksums are in response
        response = requests.get(self._url(url + '/blob'),
                                headers=self._headers())
        self.assertEqual('0825587cc011b7e76381b65e19d5ec27',
                         response.headers["Content-MD5"])
        self.assertEqual('89eb4b969b721ba8c3aff18ad7d69454f651a697',
                         response.headers["X-Openstack-Glare-Content-SHA1"])
        self.assertEqual('bbfd48c7ec792fc462e58232d4d9f407'
                         'ecefb75cc9e9823336166556b499ea4d',
                         response.headers["X-Openstack-Glare-Content-SHA256"])

        blob_data = self.get(url=url + '/blob')
        self.assertEqual(data, blob_data)

        # download artifact via admin
        self.set_user('admin')
        blob_data = self.get(url=url + '/blob')
        self.assertEqual(data, blob_data)

        # try to download blob via different user
        self.set_user('user2')
        self.get(url=url + '/blob', status=404)

    def test_blob_add_custom_location(self):
        # Create artifact
        art = self.create_artifact({'name': 'name5',
                                    'version': '1.0',
                                    'tags': ['tag1', 'tag2', 'tag3'],
                                    'int1': 2048,
                                    'float1': 987.654,
                                    'str1': 'lalala',
                                    'bool1': False,
                                    'string_required': '123'})
        self.assertIsNotNone(art['id'])

        # Create auxiliary artifact and upload data there
        aux = self.create_artifact({'name': 'auxiliary'})
        url = '/sample_artifact/%s/blob' % aux['id']
        data = b'a' * 1000
        self.put(url=url, data=data)
        data_url = self._url(url)

        # Set custom location
        url = '/sample_artifact/%s' % art['id']
        body = jsonutils.dumps(
            {'url': data_url,
             'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"})
        headers = {'Content-Type':
                   'application/vnd+openstack.glare-custom-location+json'}
        self.put(url=url + '/blob', data=body,
                 status=200, headers=headers)

        # test re-add failed
        self.put(url=url + '/blob', data=body, status=409, headers=headers)
        # add to non-existing property
        self.put(url=url + '/blob_non_exist', data=body, status=400,
                 headers=headers)

        # Get the artifact, blob property should have status 'active'
        art = self.get(url=url, status=200)
        self.assertEqual('active', art['blob']['status'])
        self.assertEqual('fake', art['blob']['md5'])
        self.assertEqual('fake_sha', art['blob']['sha1'])
        self.assertEqual('fake_sha256', art['blob']['sha256'])
        self.assertIsNone(art['blob']['size'])
        self.assertIsNone(art['blob']['content_type'])
        self.assertEqual(data_url, art['blob']['url'])
        self.assertNotIn('id', art['blob'])

        # Set custom location
        url = '/sample_artifact/%s' % art['id']
        self.put(url=url + '/dict_of_blobs/blob', data=body,
                 status=200, headers=headers)

        # Get the artifact, blob property should have status 'active'
        art = self.get(url=url, status=200)
        self.assertEqual('active', art['dict_of_blobs']['blob']['status'])
        self.assertIsNotNone(art['dict_of_blobs']['blob']['md5'])
        self.assertIsNone(art['dict_of_blobs']['blob']['size'])
        self.assertIsNone(art['dict_of_blobs']['blob']['content_type'])
        self.assertEqual(data_url, art['dict_of_blobs']['blob']['url'])
        self.assertNotIn('id', art['dict_of_blobs']['blob'])
        # test re-add failed
        self.put(url=url + '/dict_of_blobs/blob', data=body, status=409,
                 headers=headers)

        # test request failed with non-json containment
        self.put(url=url + '/dict_of_blobs/blob_incorrect', data="incorrect",
                 status=400, headers=headers)

        # delete the artifact
        self.delete(url=url)

    def test_delete_external_blob(self):
        # Create artifact
        art = self.create_artifact({'name': 'name5',
                                    'version': '1.0',
                                    'tags': ['tag1', 'tag2', 'tag3'],
                                    'int1': 2048,
                                    'float1': 987.654,
                                    'str1': 'lalala',
                                    'bool1': False,
                                    'string_required': '123'})
        self.assertIsNotNone(art['id'])

        # Create auxiliary artifact and upload data there
        aux = self.create_artifact({'name': 'auxiliary'})
        url = '/sample_artifact/%s/blob' % aux['id']
        data = b'a' * 1000
        self.put(url=url, data=data)
        data_url = self._url(url)

        # Set custom location
        url = '/sample_artifact/%s' % art['id']
        body = jsonutils.dumps(
            {'url': data_url,
             'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"})
        headers = {'Content-Type':
                   'application/vnd+openstack.glare-custom-location+json'}
        art = self.put(url=url + '/blob', data=body,
                       status=200, headers=headers)
        self.assertEqual('active', art['blob']['status'])
        self.assertEqual('fake', art['blob']['md5'])
        self.assertEqual('fake_sha', art['blob']['sha1'])
        self.assertEqual('fake_sha256', art['blob']['sha256'])
        self.assertIsNone(art['blob']['size'])
        self.assertIsNone(art['blob']['content_type'])
        self.assertEqual(data_url, art['blob']['url'])
        self.assertNotIn('id', art['blob'])

        # Delete should work
        art = self.delete(url=url + '/blob', status=200)
        self.assertIsNone(art['blob'])

        # Deletion of empty blob fails
        self.delete(url=url + '/blob', status=404)

        # Deletion of non-blob field fails
        self.delete(url=url + '/int1', status=400)

        # Deletion ofn non-existing field fails
        self.delete(url=url + '/NONEXIST', status=400)

        # Upload data
        data = 'some_arbitrary_testing_data'
        headers = {'Content-Type': 'application/octet-stream'}
        art = self.put(url=url + '/blob', data=data, status=200,
                       headers=headers)
        self.assertEqual('active', art['blob']['status'])
        md5 = hashlib.md5(data.encode('UTF-8')).hexdigest()
        sha1 = hashlib.sha1(data.encode('UTF-8')).hexdigest()
        sha256 = hashlib.sha256(data.encode('UTF-8')).hexdigest()
        self.assertEqual(md5, art['blob']['md5'])
        self.assertEqual(sha1, art['blob']['sha1'])
        self.assertEqual(sha256, art['blob']['sha256'])

        # Deletion of internal blob fails
        self.delete(url=url + '/blob', status=403)

    def test_delete_external_blob_dict(self):
        # Create artifact
        art = self.create_artifact({'name': 'name5',
                                    'version': '1.0',
                                    'tags': ['tag1', 'tag2', 'tag3'],
                                    'int1': 2048,
                                    'float1': 987.654,
                                    'str1': 'lalala',
                                    'bool1': False,
                                    'string_required': '123'})
        self.assertIsNotNone(art['id'])

        # Create auxiliary artifact and upload data there
        aux = self.create_artifact({'name': 'auxiliary'})
        url = '/sample_artifact/%s/blob' % aux['id']
        data = b'a' * 1000
        self.put(url=url, data=data)
        data_url = self._url(url)

        # Set custom location
        url = '/sample_artifact/%s' % art['id']
        body = jsonutils.dumps(
            {'url': data_url,
             'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"})
        headers = {'Content-Type':
                   'application/vnd+openstack.glare-custom-location+json'}
        art = self.put(url=url + '/dict_of_blobs/blob', data=body,
                       status=200, headers=headers)
        self.assertEqual('active', art['dict_of_blobs']['blob']['status'])
        self.assertEqual('fake', art['dict_of_blobs']['blob']['md5'])
        self.assertEqual('fake_sha', art['dict_of_blobs']['blob']['sha1'])
        self.assertEqual('fake_sha256', art['dict_of_blobs']['blob']['sha256'])
        self.assertIsNone(art['dict_of_blobs']['blob']['size'])
        self.assertIsNone(art['dict_of_blobs']['blob']['content_type'])
        self.assertEqual(data_url, art['dict_of_blobs']['blob']['url'])
        self.assertNotIn('id', art['dict_of_blobs']['blob'])

        # Delete should work
        art = self.delete(url=url + '/dict_of_blobs/blob', status=200)
        self.assertNotIn('blob', art['dict_of_blobs'])

        # Deletion of non-existing blob fails
        self.delete(url=url + '/dict_of_blobs/NONEXIST', status=404)

        # Upload data
        data = 'some_arbitrary_testing_data'
        headers = {'Content-Type': 'application/octet-stream'}
        art = self.put(url=url + '/dict_of_blobs/blob', data=data, status=200,
                       headers=headers)
        self.assertEqual('active', art['dict_of_blobs']['blob']['status'])
        md5 = hashlib.md5(data.encode('UTF-8')).hexdigest()
        sha1 = hashlib.sha1(data.encode('UTF-8')).hexdigest()
        sha256 = hashlib.sha256(data.encode('UTF-8')).hexdigest()
        self.assertEqual(md5, art['dict_of_blobs']['blob']['md5'])
        self.assertEqual(sha1, art['dict_of_blobs']['blob']['sha1'])
        self.assertEqual(sha256, art['dict_of_blobs']['blob']['sha256'])

        # Deletion of internal blob fails
        self.delete(url=url + '/dict_of_blobs/blob', status=403)

    def test_internal_location(self):
        self.set_user('admin')
        # Create artifact
        art = self.create_artifact({'name': 'name5'})
        self.assertIsNotNone(art['id'])

        url = '/sample_artifact/%s' % art['id']
        headers = {'Content-Type':
                   'application/vnd+openstack.glare-custom-location+json'}

        # Setting locations with forbidden schemes fails
        forbidden_schemes = ('file', 'filesystem', 'swift+config', 'sql')
        for scheme in forbidden_schemes:
            body = jsonutils.dumps(
                {'md5': 'fake', 'sha1': 'fake_sha', 'sha256': 'fake_sha256',
                 'location_type': 'internal',
                 'url': scheme + '://FAKE_LOCATION.com'})
            self.put(url=url + '/blob', data=body, status=403, headers=headers)

        # Setting locations with unknown schemes fail
        body = jsonutils.dumps(
            {'md5': 'fake', 'sha1': 'fake_sha', 'sha256': 'fake_sha256',
             'location_type': 'internal',
             'url': 'UNKNOWN://FAKE_LOCATION.com'})
        self.put(url=url + '/blob', data=body, status=400, headers=headers)

        body = jsonutils.dumps(
            {'md5': 'fake', 'sha1': 'fake_sha', 'sha256': 'fake_sha256',
             'location_type': 'internal',
             'url': 'https://FAKE_LOCATION.com'})
        art = self.put(url=url + '/blob', data=body, status=200,
                       headers=headers)

        self.assertFalse(art['blob']['external'])
        self.assertEqual('active', art['blob']['status'])
        self.assertEqual('fake', art['blob']['md5'])
        self.assertEqual('fake_sha', art['blob']['sha1'])
        self.assertEqual('fake_sha256', art['blob']['sha256'])
        self.assertIsNone(art['blob']['size'])
        self.assertIsNone(art['blob']['content_type'])
        self.assertEqual('/artifacts/sample_artifact/%s/blob' % art['id'],
                         art['blob']['url'])
        self.assertNotIn('id', art['blob'])


class TestTags(base.TestArtifact):
    def test_tags(self):
        # Create artifact
        art = self.create_artifact({'name': 'name5',
                                    'version': '1.0',
                                    'tags': ['tag1', 'tag2', 'tag3'],
                                    'int1': 2048,
                                    'float1': 987.654,
                                    'str1': 'lalala',
                                    'bool1': False,
                                    'string_required': '123'})
        self.assertIsNotNone(art['id'])

        url = '/sample_artifact/%s' % art['id']
        data = [{
            "op": "replace",
            "path": "/status",
            "value": "active"
        }]
        art = self.patch(url=url, data=data, status=200)
        self.assertEqual('active', art['status'])
        art = self.admin_action(art['id'], self.make_public)

        self.assertEqual('public', art['visibility'])
        # only admins can update tags for public artifacts
        self.set_user("admin")

        # Check that tags created correctly
        url = '/sample_artifact/%s' % art['id']
        resp = self.get(url=url, status=200)
        for tag in ['tag1', 'tag2', 'tag3']:
            self.assertIn(tag, resp['tags'])

        # Set new tag list to the art
        body = [{"op": "replace",
                 "path": "/tags",
                 "value": ["new_tag1", "new_tag2", "new_tag3"]}]
        resp = self.patch(url=url, data=body, status=200)
        for tag in ['new_tag1', 'new_tag2', 'new_tag3']:
            self.assertIn(tag, resp['tags'])

        # Delete all tags from the art
        body = [{"op": "replace",
                 "path": "/tags",
                 "value": []}]
        resp = self.patch(url=url, data=body, status=200)
        self.assertEqual([], resp['tags'])

        # Set new tags as null
        body = [{"op": "replace",
                 "path": "/tags",
                 "value": None}]
        resp = self.patch(url=url, data=body, status=200)
        self.assertEqual([], resp['tags'])

        # Get the list of tags
        resp = self.get(url=url, status=200)
        self.assertEqual([], resp['tags'])


class TestArtifactOps(base.TestArtifact):
    def test_create(self):
        """All tests related to artifact creation"""
        # check that cannot create artifact for non-existent artifact type
        self.post('/incorrect_artifact', {"name": "t"}, status=404)
        # check that cannot accept non-json body
        self.post('/incorrect_artifact', "incorrect_body", status=400)
        # check that cannot accept incorrect content type
        self.post('/sample_artifact', {"name": "t"}, status=415,
                  headers={"Content-Type": "application/octet-stream"})
        # check that cannot create artifact without name
        self.create_artifact(data={"int1": 1024}, status=400)
        # check that cannot create artifact with too long name
        self.create_artifact(data={"name": "t" * 256}, status=400)
        # check that cannot create artifact with empty name
        self.create_artifact(data={"name": ""}, status=400)
        # check that can create af without version
        private_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str"})
        # check that default is set on artifact create
        uuid.UUID(private_art['id'])
        self.assertEqual('0.0.0', private_art['version'])
        self.assertEqual("default", private_art["system_attribute"])
        self.assertEqual(self.users['user1']['tenant_id'],
                         private_art['owner'])

        # check that cannot create artifact with invalid version
        self.create_artifact(data={"name": "test_af",
                                   "version": "dummy_version"}, status=400)
        # check that cannot create artifact with empty and long version
        self.create_artifact(data={"name": "test_af",
                                   "version": ""}, status=400)
        # check that cannot create artifact with empty and long version
        self.create_artifact(data={"name": "test_af",
                                   "version": "t" * 256}, status=400)
        # check that artifact artifact with the same name-version cannot
        # be created
        self.create_artifact(data={"name": "test_af"}, status=409)
        # check that we cannot create af with the same version but different
        # presentation
        self.create_artifact(data={"name": "test_af", "version": "0.0"},
                             status=409)
        # check that we can create artifact with different version and tags
        new_af = self.create_artifact(
            data={"name": "test_af", "version": "0.0.1",
                  "tags": ["tag1", "tag2"]})
        self.assertEqual({"tag1", "tag2"}, set(new_af["tags"]))
        # check that we cannot create artifact with visibility
        self.create_artifact(data={"name": "test_af", "version": "0.0.2",
                                   "visibility": "private"}, status=400)
        # check that we cannot create artifact with system property
        self.create_artifact(data={"name": "test_af", "version": "0.0.2",
                                   "system_attribute": "test"}, status=403)
        # check that we cannot specify blob in create
        self.create_artifact(data={"name": "test_af", "version": "0.0.2",
                                   "blob": {
                                       'url': None, 'size': None,
                                       'md5': None, 'status': 'saving',
                                       'external': False}}, status=400)
        # check that anonymous user cannot create artifact
        self.set_user("anonymous")
        self.create_artifact(data={"name": "test_af", "version": "0.0.2"},
                             status=403)
        # check that another user can create artifact
        # with the same name version
        self.set_user("user2")
        some_af = self.create_artifact(data={"name": "test_af"})

        # check we can create artifact with all available attributes
        # (except blobs and system)
        expected = {
            "name": "test_big_create",
            "link1": "/artifacts/sample_artifact/%s" % some_af['id'],
            "bool1": True,
            "int1": 2323,
            "float1": 0.1,
            "str1": "test",
            "list_of_str": ["test"],
            "list_of_int": [0],
            "dict_of_str": {"test": "test"},
            "dict_of_int": {"test": 0},
            "string_mutable": "test",
            "string_required": "test",
        }
        big_af = self.create_artifact(data=expected)
        actual = {}
        for k in expected:
            actual[k] = big_af[k]
        self.assertEqual(expected, actual)
        # check that we cannot access artifact from other user
        # check that active artifact is not available for other user
        url = '/sample_artifact/%s' % private_art['id']
        self.get(url, status=404)
        # check we cannot create af with non-existing property
        self.create_artifact(data={"name": "test_af_ne",
                                   "non_exist": "non_exist"}, status=400)
        # activate and publish artifact to check that we can create
        # private artifact with the same name version
        self.set_user("user1")

        self.patch(url=url, data=self.make_active)
        self.admin_action(private_art['id'], self.make_public)
        self.create_artifact(data={"name": "test_af",
                                   "string_required": "test_str"})

        # Check we cannot create data with display_type_name.
        self.create_artifact(data={"display_type_name": "Sample Artifact",
                                   "name": "Invalid_data"}, status=400)

    def test_activate(self):
        # create artifact to update
        private_art = self.create_artifact(
            data={"name": "test_af",
                  "version": "0.0.1"})
        # cannot activate artifact without required for activate attributes
        url = '/sample_artifact/%s' % private_art['id']
        self.patch(url=url, data=self.make_active, status=403)
        add_required = [{
            "op": "replace",
            "path": "/string_required",
            "value": "string"
        }]
        self.patch(url=url, data=add_required)
        # can activate if body contains non status changes
        make_active_with_updates = self.make_active + [{"op": "replace",
                                                        "path": "/description",
                                                        "value": "test"}]
        active_art = self.patch(url=url, data=make_active_with_updates)
        private_art['status'] = 'active'
        private_art['activated_at'] = active_art['activated_at']
        private_art['updated_at'] = active_art['updated_at']
        private_art['string_required'] = 'string'
        private_art['description'] = 'test'
        self.assertEqual(private_art, active_art)
        # check that active artifact is not available for other user
        self.set_user("user2")
        self.get(url, status=404)
        self.set_user("user1")

        # test that activate is idempotent
        self.patch(url=url, data=self.make_active)
        # test activate deleted artifact
        self.delete(url=url)
        self.patch(url=url, data=self.make_active, status=404)

    def test_publish(self):
        # create artifact to update
        self.set_user('admin')
        private_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})

        url = '/sample_artifact/%s' % private_art['id']
        # test that we cannot publish drafted artifact
        self.patch(url=url, data=self.make_public, status=403)

        self.patch(url=url, data=self.make_active)

        # test that cannot publish deactivated artifact
        self.patch(url, data=self.make_deactivated)
        self.patch(url, data=self.make_public, status=403)

        self.patch(url=url, data=self.make_active)

        # test that visibility can be specified in the request with
        # other updates
        make_public_with_updates = self.make_public + [
            {"op": "replace",
             "path": "/string_mutable",
             "value": "test"}]
        self.patch(url=url, data=make_public_with_updates)
        # check public artifact
        public_art = self.patch(url=url, data=self.make_public)
        private_art['activated_at'] = public_art['activated_at']
        private_art['visibility'] = 'public'
        private_art['status'] = 'active'
        private_art['updated_at'] = public_art['updated_at']
        private_art['string_mutable'] = 'test'
        self.assertEqual(private_art, public_art)
        # check that public artifact available for simple user
        self.set_user("user1")
        self.get(url)
        self.set_user("admin")
        # test that artifact publish with the same name and version failed
        duplicate_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        dup_url = '/sample_artifact/%s' % duplicate_art['id']
        # proceed with duplicate testing
        self.patch(url=dup_url, data=self.make_active)
        self.patch(url=dup_url, data=self.make_public, status=409)

    def test_delete(self):
        # try ro delete not existing artifact
        url = '/sample_artifact/111111'
        self.delete(url=url, status=404)

        # check that we can delete artifact with soft link
        art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        artd = self.create_artifact(
            data={"name": "test_afd", "string_required": "test_str",
                  "version": "0.0.1",
                  "link1": '/artifacts/sample_artifact/%s' % art['id']})

        url = '/sample_artifact/%s' % artd['id']
        self.delete(url=url, status=204)

        # try to change status of artifact to deleting
        url = '/sample_artifact/%s' % art['id']
        patch = [{'op': 'replace',
                  'value': 'deleting',
                  'path': '/status'}]
        self.patch(url=url, data=patch, status=400)

        # delete artifact via different user (non admin)
        self.set_user('user2')
        self.delete(url=url, status=404)

        # delete artifact via admin user
        self.set_user('admin')
        self.delete(url=url, status=204)

        # delete public artifact via different user
        self.set_user('user1')
        art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        url = '/sample_artifact/%s' % art['id']
        self.patch(url=url, data=self.make_active)
        self.admin_action(art['id'], self.make_public)
        self.set_user('user2')
        self.delete(url=url, status=403)

        self.set_user('user1')
        self.delete(url=url, status=403)
        self.set_user('admin')
        self.delete(url=url)

        # delete deactivated artifact
        art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        url = '/sample_artifact/%s' % art['id']
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_deactivated)
        self.delete(url=url, status=204)
        self.get(url=url, status=404)
        self.assertEqual(0, len(self.get(
            url='/sample_artifact')['artifacts']))

    def test_deactivate(self):
        # test artifact deactivate for non-active artifact
        private_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        url = '/sample_artifact/%s' % private_art['id']
        self.admin_action(private_art['id'], self.make_deactivated, 403)
        self.patch(url, self.make_active)
        self.set_user('admin')
        # test can deactivate if there is something else in request
        make_deactived_with_updates = [
            {"op": "replace",
             "path": "/description",
             "value": "test"}] + self.make_deactivated
        # test artifact deactivate success
        deactivated_art = self.admin_action(
            private_art['id'], make_deactived_with_updates)
        self.assertEqual("deactivated", deactivated_art["status"])
        self.assertEqual("test", deactivated_art["description"])
        # test deactivate is idempotent
        self.patch(url, self.make_deactivated)

    def test_reactivate(self):
        self.set_user('admin')
        private_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})
        url = '/sample_artifact/%s' % private_art['id']
        self.patch(url, self.make_active)
        self.admin_action(private_art['id'], self.make_deactivated)
        # test can reactivate if there is something else in request
        make_reactived_with_updates = self.make_active + [
            {"op": "replace",
             "path": "/description",
             "value": "test"}]
        # test artifact deactivate success
        reactivated_art = self.admin_action(
            private_art['id'], make_reactived_with_updates)
        self.assertEqual("active", reactivated_art["status"])
        self.assertEqual("test", reactivated_art["description"])


class TestUpdate(base.TestArtifact):
    def test_update_artifact_before_activate(self):
        """Test updates for artifact before activation"""
        # create artifact to update
        private_art = self.create_artifact(data={"name": "test_af"})
        url = '/sample_artifact/%s' % private_art['id']
        # check we can update artifact
        change_version = [{
            "op": "replace",
            "path": "/version",
            "value": "0.0.2"
        }]
        self.patch(url=url, data=change_version)

        # wrong patch format fails with 400 error
        invalid_patch = {
            "op": "replace",
            "path": "/version",
            "value": "0.0.2"
        }
        self.patch(url=url, data=invalid_patch, status=400)

        # check that we cannot update af if af with
        # the same name or version exists
        dup_version = self.create_artifact(
            data={"name": "test_af", "version": "0.0.1"})
        dupv_url = '/sample_artifact/%s' % dup_version['id']
        change_version_dup = [{
            "op": "replace",
            "path": "/version",
            "value": "0.0.2"
        }]
        self.patch(url=dupv_url, data=change_version_dup, status=409)

        dup_name = self.create_artifact(data={"name": "test_name_af",
                                              "version": "0.0.2"})
        dupn_url = '/sample_artifact/%s' % dup_name['id']
        change_name = [{
            "op": "replace",
            "path": "/name",
            "value": "test_af"
        }]
        self.patch(url=dupn_url, data=change_name, status=409)
        # check that we can update artifacts dup
        # after first artifact updated name and version
        change_version[0]['value'] = "0.0.3"
        self.patch(url=url, data=change_version)
        self.patch(url=dupn_url, data=change_name)
        # check that we can update artifact dupv to target version
        # also check that after deletion of artifact with the same name
        # version I can update dupv
        self.delete(dupn_url)
        self.patch(url=dupv_url, data=change_version_dup)
        # check we cannot update artifact with incorrect content-type
        self.patch(url, {}, status=415,
                   headers={"Content-Type": "application/json"})
        # check we cannot update tags with patch
        set_tags = [{
            "op": "replace",
            "path": "/tags",
            "value": "test_af"
        }]
        self.patch(url, set_tags, status=400)
        # check we cannot update artifact with incorrect json-patch
        self.patch(url, "incorrect json patch", status=400)
        # check update is correct if there is no update
        no_name_update = [{
            "op": "replace",
            "path": "/name",
            "value": "test_af"
        }]
        self.patch(url, no_name_update)
        # check add new property request rejected
        add_prop = [{
            "op": "add",
            "path": "/string1",
            "value": "test_af"
        }]
        self.patch(url, add_prop, 400)
        # check delete property request rejected
        add_prop[0]["op"] = "remove"
        add_prop[0]["path"] = "/string_required"
        self.patch(url, add_prop, 400)
        # check we cannot update system attr with patch
        system_attr = [{
            "op": "replace",
            "path": "/system_attribute",
            "value": "dummy"
        }]
        self.patch(url, system_attr, 403)
        # check cannot update blob attr with patch
        blob_attr = [{
            "op": "replace",
            "path": "/blob",
            "value": {"name": "test_af", "version": "0.0.2",
                      "blob": {'url': None, 'size': None, 'md5': None,
                               'status': 'saving', 'external': False}}}]
        self.patch(url, blob_attr, 400)
        blob_attr[0]["path"] = "/dict_of_blobs/-"
        blob_attr[0]["op"] = "add"
        self.patch(url, blob_attr, 400)
        # test update correctness for all attributes
        big_update_patch = [
            {"op": "replace", "path": "/bool1", "value": True},
            {"op": "replace", "path": "/int1", "value": 2323},
            {"op": "replace", "path": "/float1", "value": 0.1},
            {"op": "replace", "path": "/str1", "value": "test"},
            {"op": "replace", "path": "/list_of_str", "value": ["test"]},
            {"op": "replace", "path": "/list_of_int", "value": [0]},
            {"op": "replace", "path": "/dict_of_str",
             "value": {"test": "test"}},
            {"op": "replace", "path": "/dict_of_int",
             "value": {"test": 0}},
            {"op": "replace", "path": "/string_mutable", "value": "test"},
            {"op": "replace", "path": "/string_required", "value": "test"},
        ]
        upd_af = self.patch(url, big_update_patch)
        for patch_item in big_update_patch:
            self.assertEqual(patch_item.get("value"),
                             upd_af[patch_item.get("path")[1:]])

        # check we can update private artifact
        # to the same name version as public artifact
        self.patch(url=url, data=self.make_active)
        self.admin_action(private_art['id'], self.make_public)
        self.patch(url=dupv_url, data=change_version)

    def test_update_after_activate_and_publish(self):
        # activate artifact
        private_art = self.create_artifact(
            data={"name": "test_af", "string_required": "test_str",
                  "version": "0.0.1"})

        url = '/sample_artifact/%s' % private_art['id']
        self.patch(url=url, data=self.make_active)
        # test that immutable properties cannot be updated
        upd_immutable = [{
            "op": "replace",
            "path": "/name",
            "value": "new_name"
        }]
        self.patch(url, upd_immutable, status=403)
        # test that mutable properties can be updated
        upd_mutable = [{
            "op": "replace",
            "path": "/string_mutable",
            "value": "new_value"
        }]
        updated_af = self.patch(url, upd_mutable)
        self.assertEqual("new_value", updated_af["string_mutable"])
        # test cannot update deactivated artifact
        upd_mutable[0]["value"] = "another_new_value"
        self.admin_action(private_art['id'], self.make_deactivated)
        # test that nobody(even admin) can publish deactivated artifact
        self.set_user("admin")
        self.patch(url, self.make_public, 403)
        self.set_user("user1")
        self.patch(url, upd_mutable, 403)
        self.admin_action(private_art['id'], self.make_active)
        # publish artifact
        self.admin_action(private_art['id'], self.make_public)
        # check we cannot update public artifact anymore
        self.patch(url, upd_mutable, status=403)
        self.patch(url, upd_mutable, status=403)
        # check that admin can update public artifact
        self.set_user("admin")
        self.patch(url, upd_mutable)

    def test_update_with_validators(self):
        data = {'name': 'test_af',
                'version': '0.0.1',
                'list_validators': ['a', 'b', 'c'],
                'dict_validators': {'abc': 'a', 'def': 'b'}}
        art = self.create_artifact(data=data)
        url = '/sample_artifact/%s' % art['id']

        # min int_validators value is 10
        patch = [{"op": "replace", "path": "/int_validators", "value": 9}]
        self.patch(url=url, data=patch, status=400)

        # max int_validators value is 20
        patch = [{"op": "replace", "path": "/int_validators", "value": 21}]
        self.patch(url=url, data=patch, status=400)

        # number 15 is okay
        patch = [{"op": "replace", "path": "/int_validators", "value": 15}]
        self.patch(url=url, data=patch, status=200)

        # max string length is 255
        patch = [{"op": "replace", "path": "/str1", "value": 'd' * 256}]
        self.patch(url=url, data=patch, status=400)

        # 'cc' is not allowed value for the string
        patch = [{"op": "replace", "path": "/string_validators",
                  "value": 'cc'}]
        self.patch(url=url, data=patch, status=400)

        # 'aa' is okay
        patch = [{"op": "replace", "path": "/string_validators",
                  "value": 'aa'}]
        self.patch(url=url, data=patch)

        # 'bb' is okay too
        patch = [{"op": "replace", "path": "/string_validators",
                  "value": 'bb'}]
        self.patch(url=url, data=patch)

        # even if 'c' * 11 is allowed value it exceeds MaxLen's 10 character
        # limit
        patch = [{"op": "replace", "path": "/string_validators",
                  "value": 'c' * 11}]
        self.patch(url=url, data=patch, status=400)

        # string_regex format it '^([0-9a-fA-F]){8}$'
        patch = [{"op": "replace", "path": "/string_regex",
                  "value": 'INVALID'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/string_regex",
                  "value": '167f808Z'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/string_regex",
                  "value": '167f80835'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/string_regex",
                  "value": '167f8083'}]
        self.patch(url=url, data=patch)

        # test list has 3 elements maximum
        patch = [{"op": "add", "path": "/list_validators/-", "value": 'd'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/list_validators",
                  "value": ['a', 'b', 'c', 'd']}]
        self.patch(url=url, data=patch, status=400)

        # test list values are unique
        patch = [{"op": "replace", "path": "/list_validators/2", "value": 'b'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/list_validators",
                  "value": ['a', 'b', 'b']}]
        self.patch(url=url, data=patch, status=400)

        # regular update works
        patch = [{"op": "replace", "path": "/list_validators/1", "value": 'd'}]
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['list_validators'], ['a', 'd', 'c'])

        patch = [{"op": "replace", "path": "/list_validators",
                  "value": ['c', 'b', 'a']}]
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['list_validators'], ['c', 'b', 'a'])

        # test adding wrong key to dict
        patch = [{"op": "add", "path": "/dict_validators/aaa", "value": 'b'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/dict_validators",
                  "value": {'abc': 'a', 'def': 'b', 'aaa': 'c'}}]
        self.patch(url=url, data=patch, status=400)

        # test dict has 3 elements maximum
        patch = [{"op": "add", "path": "/dict_validators/ghi", "value": 'd'}]
        self.patch(url=url, data=patch)

        patch = [{"op": "add", "path": "/dict_validators/jkl", "value": 'd'}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace", "path": "/dict_validators",
                  "value": {'abc': 'a', 'def': 'b', 'ghi': 'c', 'jkl': 'd'}}]
        self.patch(url=url, data=patch, status=400)

        # regular update works
        patch = [{"op": "replace", "path": "/dict_validators/abc",
                  "value": "q"}]
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['dict_validators'],
                         {'abc': 'q', 'def': 'b', 'ghi': 'd'})

        patch = [{"op": "replace", "path": "/dict_validators",
                  "value": {'abc': 'l', 'def': 'x', 'ghi': 'z'}}]
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['dict_validators'],
                         {'abc': 'l', 'def': 'x', 'ghi': 'z'})

    def test_update_base_fields(self):
        data = {'name': 'test_af',
                'version': '0.0.1'}
        art = self.create_artifact(data=data)
        url = '/sample_artifact/%s' % art['id']

        # INT
        # float to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": 1.1}]
        art = self.patch(url=url, data=patch)
        self.assertEqual(1, art['int1'])

        # str(int) to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": '2'}]
        art = self.patch(url=url, data=patch)
        self.assertEqual(2, art['int1'])

        # str(float) to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": '3.0'}]
        self.patch(url=url, data=patch, status=400)

        # str(int) to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": ''}]
        self.patch(url=url, data=patch, status=400)

        # empty list to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": []}]
        self.patch(url=url, data=patch, status=400)

        # empty dict to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": {}}]
        self.patch(url=url, data=patch, status=400)

        # bool to int
        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": True}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(1, art['int1'])

        patch = [{"op": "replace",
                  "path": "/int1",
                  "value": False}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(0, art['int1'])

        # FLOAT
        # int to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": 1}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(1.0, art['float1'])

        # str(int) to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": '2'}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(2.0, art['float1'])

        # str(int) to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": []}]
        self.patch(url=url, data=patch, status=400)

        # str(int) to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": {}}]
        self.patch(url=url, data=patch, status=400)

        # str(bool) to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": 'True'}]
        self.patch(url=url, data=patch, status=400)

        # bool to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": True}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(1.0, art['float1'])

        # str(float) to float
        patch = [{"op": "replace",
                  "path": "/float1",
                  "value": '3.0'}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(3.0, art['float1'])

        # STRING
        # str to str
        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": '3.0'}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual('3.0', art['str1'])

        # int to str
        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": 1}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual('1', art['str1'])

        # float to str
        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": 1.0}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual('1.0', art['str1'])

        # bool to str
        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": True}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual('True', art['str1'])

        # empty list to str
        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": []}]
        self.patch(url=url, data=patch, status=400)

        patch = [{"op": "replace",
                  "path": "/str1",
                  "value": {}}]
        self.patch(url=url, data=patch, status=400)

        # BOOL
        # int to bool
        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": 1}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(True, art['bool1'])

        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": 0}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        # float to bool
        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": 2.1}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": 1.1}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        # string to bool
        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": '1'}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(True, art['bool1'])

        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": ''}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])
        # [] to bool
        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": []}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": [1]}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])
        # {} to bool
        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": {}}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        patch = [{"op": "replace",
                  "path": "/bool1",
                  "value": {'1', 1}}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(False, art['bool1'])

        # LIST OF STR AND INT
        # {} to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": {}}]
        self.patch(url=url, data=patch, status=400)

        # [] to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": []}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual([], art['list_of_str'])

        # list of int to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": [1, 2, 3]}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(['1', '2', '3'], art['list_of_str'])

        # list of bool to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": [True, False, True]}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual(['True', 'False', 'True'], art['list_of_str'])

        # str to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": '123'}]
        self.patch(url=url, data=patch, status=400)

        # int to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": 11}]
        self.patch(url=url, data=patch, status=400)

        # bool to list of str
        patch = [{"op": "replace",
                  "path": "/list_of_str",
                  "value": True}]
        self.patch(url=url, data=patch, status=400)

        # Dict OF INT
        # [] to dict of int
        patch = [{"op": "replace",
                  "path": "/dict_of_int",
                  "value": []}]
        self.patch(url=url, data=patch, status=400)

        # {} to dict of int
        patch = [{"op": "replace",
                  "path": "/dict_of_int",
                  "value": {}}]
        art = self.patch(url=url, data=patch, status=200)
        self.assertEqual({}, art['dict_of_int'])

        # int to dict of int
        patch = [{"op": "replace",
                  "path": "/dict_of_int",
                  "value": 1}]
        self.patch(url=url, data=patch, status=400)

        # bool to dict of int
        patch = [{"op": "replace",
                  "path": "/dict_of_int",
                  "value": True}]
        self.patch(url=url, data=patch, status=400)

        # string to dict of int
        patch = [{"op": "replace",
                  "path": "/dict_of_int",
                  "value": 'aaa'}]
        self.patch(url=url, data=patch, status=400)

    def test_update_field_dict(self):
        art1 = self.create_artifact(data={"name": "art1"})

        # create artifact without dict prop
        data = {'name': 'art_without_dict'}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual({}, result['dict_of_str'])

        # create artifact with dict prop
        data = {'name': 'art_with_dict',
                'dict_of_str': {'a': '1', 'b': '3'}}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual({'a': '1', 'b': '3'}, result['dict_of_str'])

        # create artifact with empty dict
        data = {'name': 'art_with_empty_dict',
                'dict_of_str': {}}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual({}, result['dict_of_str'])

        # add element in invalid path
        data = [{'op': 'add',
                 'path': '/dict_of_str',
                 'value': 'val1'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # add new element
        data = [{'op': 'add',
                 'path': '/dict_of_str/new',
                 'value': 'val1'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual('val1', result['dict_of_str']['new'])

        # add existent element
        data = [{'op': 'add',
                 'path': '/dict_of_str/new',
                 'value': 'val_new'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual('val_new', result['dict_of_str']['new'])

        # add element with empty key
        data = [{'op': 'add',
                 'path': '/dict_of_str/',
                 'value': 'val1'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # replace element
        data = [{'op': 'replace',
                 'path': '/dict_of_str/new',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual('val2', result['dict_of_str']['new'])

        # replace non-existent element
        data = [{'op': 'replace',
                 'path': '/dict_of_str/non_exist',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # remove element
        data = [{'op': 'remove',
                 'path': '/dict_of_str/new',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertIsNone(result['dict_of_str'].get('new'))

        # remove non-existent element
        data = [{'op': 'remove',
                 'path': '/dict_of_str/non_exist',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # set value
        data = [{'op': 'add',
                 'path': '/dict_of_str',
                 'value': {'key1': 'val1', 'key2': 'val2'}}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({'key1': 'val1', 'key2': 'val2'},
                         result['dict_of_str'])

        # replace value
        data = [{'op': 'add',
                 'path': '/dict_of_str',
                 'value': {'key11': 'val1', 'key22': 'val2'}}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({'key11': 'val1', 'key22': 'val2'},
                         result['dict_of_str'])

        # remove value
        data = [{'op': 'add',
                 'path': '/dict_of_str',
                 'value': {}}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({},
                         result['dict_of_str'])

        # set an element of the wrong non-conversion type value
        data = [{'op': 'add',
                 'path': '/dict_of_str/wrong_type',
                 'value': [1, 2, 4]}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # set an element of the wrong conversion type value
        data = [{'op': 'add',
                 'path': '/dict_of_str/wrong_type',
                 'value': 1}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual('1', result['dict_of_str']['wrong_type'])

        # add element with None value
        data = [{'op': 'add',
                 'path': '/dict_of_blob/nane_value',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # data add tags and metadata to artifact
        data = [{'op': 'add',
                 'path': '/tags/0',
                 'value': 'tag1'},
                {'op': 'add',
                 'path': '/tags/1',
                 'value': 'tag2'},
                {'op': 'add',
                 'path': '/metadata/meta1',
                 'value': 'value1'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['tag1', 'tag2'], sorted(result['tags']))
        self.assertEqual({'meta1': 'value1'}, result['metadata'])

        # Tags is set data structure so sequence of data is not fixed
        first_tag = result['tags'][0]
        second_tag = result['tags'][1]

        # move tag to metadata
        data = [{"op": "move",
                 "from": "/tags/0",
                 "path": "/metadata/meta2"}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual([second_tag], result['tags'])
        self.assertEqual({'meta1': 'value1', 'meta2': first_tag},
                         result['metadata'])

        # move data from one dict to another one
        data = [{"op": "move",
                 "from": "/dict_of_str/wrong_type",
                 "path": "/metadata/wrong_type"}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({}, result['dict_of_str'])
        self.assertEqual({'meta1': 'value1',
                          'meta2': first_tag,
                          'wrong_type': '1'}, result['metadata'])

        # move data from one data to another one having same key

        data = [{"op": "add",
                 "path": "/dict_of_str/new_key",
                 "value": "new_value"},
                {"op": "add",
                 "path": "/metadata/new_key",
                 "value": "new_value"}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({"new_key": "new_value"}, result['dict_of_str'])
        self.assertEqual({'meta1': 'value1',
                          'meta2': first_tag,
                          'wrong_type': '1',
                          "new_key": "new_value"}, result['metadata'])

        data = [{"op": "move",
                 "from": "/dict_of_str/new_key",
                 "path": "/metadata/new_key"}]
        result = self.patch(url=url, data=data)
        self.assertEqual({}, result['dict_of_str'])
        self.assertEqual({'meta1': 'value1',
                          'meta2': first_tag,
                          'wrong_type': '1',
                          "new_key": "new_value"}, result['metadata'])

    def test_update_field_list(self):
        art1 = self.create_artifact(data={"name": "art1"})

        # create artifact without list prop
        data = {'name': 'art_without_list'}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual([], result['list_of_str'])

        # create artifact with list prop
        data = {'name': 'art_with_list',
                'list_of_str': ['a', 'b']}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual(['a', 'b'], result['list_of_str'])

        # create artifact with empty list
        data = {'name': 'art_with_empty_list',
                'list_of_str': []}
        result = self.post(url='/sample_artifact', status=201, data=data)
        self.assertEqual([], result['list_of_str'])

        # add value
        data = [{'op': 'add',
                 'path': '/list_of_str',
                 'value': ['b', 'd']}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['b', 'd'], result['list_of_str'])

        # replace value
        data = [{'op': 'replace',
                 'path': '/list_of_str',
                 'value': ['aa', 'dd']}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['aa', 'dd'], result['list_of_str'])

        # remove value
        data = [{'op': 'add',
                 'path': '/list_of_str',
                 'value': []}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual([], result['list_of_str'])

        # add new element on empty list
        self.assertEqual([], art1['list_of_str'])
        data = [{'op': 'add',
                 'path': '/list_of_str/-',
                 'value': 'val1'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val1'], result['list_of_str'])

        # add new element on index
        data = [{'op': 'add',
                 'path': '/list_of_str/0',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val2', 'val1'], result['list_of_str'])

        # add new element on next index
        data = [{'op': 'add',
                 'path': '/list_of_str/1',
                 'value': 'val3'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val2', 'val3', 'val1'], result['list_of_str'])

        # add new element on default index
        data = [{'op': 'add',
                 'path': '/list_of_str/-',
                 'value': 'val4'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val2', 'val3', 'val1', 'val4'],
                         result['list_of_str'])

        # add new element on non-existent index
        data = [{'op': 'add',
                 'path': '/list_of_str/10',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # replace element on index
        data = [{'op': 'replace',
                 'path': '/list_of_str/1',
                 'value': 'val_new'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val2', 'val_new', 'val1', 'val4'],
                         result['list_of_str'])

        # replace element on default index
        data = [{'op': 'replace',
                 'path': '/list_of_str/-',
                 'value': 'val-'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # replace new element on non-existent index
        data = [{'op': 'replace',
                 'path': '/list_of_str/99',
                 'value': 'val_new'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # remove element on index
        data = [{'op': 'remove',
                 'path': '/list_of_str/1',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(['val2', 'val1', 'val4'], result['list_of_str'])

        # remove element on default index
        data = [{'op': 'remove',
                 'path': '/list_of_str/-',
                 'value': 'val3'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        # remove new element on non-existent index
        data = [{'op': 'remove',
                 'path': '/list_of_str/999',
                 'value': 'val2'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

    def test_update_remove_properties(self):
        data = {
            "name": "test_big_create",
            "version": "1.0.0",
            "bool1": True,
            "int1": 2323,
            "float1": 0.1,
            "str1": "test",
            "list_of_str": ["test1", "test2"],
            "list_of_int": [0, 1, 2],
            "dict_of_str": {"test": "test"},
            "dict_of_int": {"test": 0},
            "string_mutable": "test",
            "string_required": "test",
        }
        art1 = self.create_artifact(data=data)

        # remove the whole list of strings
        data = [{'op': 'replace',
                 'path': '/list_of_str',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual([], result['list_of_str'])

        # remove the whole list of ints
        data = [{'op': 'replace',
                 'path': '/list_of_int',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual([], result['list_of_int'])

        # remove the whole dict of strings
        data = [{'op': 'replace',
                 'path': '/dict_of_str',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({}, result['dict_of_str'])

        # remove the whole dict of ints
        data = [{'op': 'replace',
                 'path': '/dict_of_int',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual({}, result['dict_of_int'])

        # remove bool1
        data = [{'op': 'replace',
                 'path': '/bool1',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertEqual(False, result['bool1'])

        # remove int1
        data = [{'op': 'replace',
                 'path': '/int1',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertIsNone(result['int1'])

        # remove float1
        data = [{'op': 'replace',
                 'path': '/float1',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        result = self.patch(url=url, data=data)
        self.assertIsNone(result['float1'])

        # cannot remove id, because it's a system field
        data = [{'op': 'replace',
                 'path': '/id',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=403)

        # cannot remove name
        data = [{'op': 'replace',
                 'path': '/name',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        headers = {'Content-Type': 'application/octet-stream'}
        self.put(url=url + '/blob', data="d" * 1000, headers=headers)

        # cannot remove blob
        data = [{'op': 'replace',
                 'path': '/blob',
                 'value': None}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

    def test_update_malformed_json_patch(self):
        data = {'name': 'ttt'}
        art1 = self.create_artifact(data=data)

        data = [{'op': 'replace', 'path': None, 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '/', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '//', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': 'name/', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '*/*', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': None, 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': '/', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': '//', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': 'name/', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': '*/*', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'add', 'path': '/name'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': None}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '/'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '//'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': 'name/'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'replace', 'path': '*/*'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

        data = [{'op': 'no-op', 'path': '/name', 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)

    def test_update_invalid_activation(self):
        data = {'name': 'ttt'}
        art1 = self.create_artifact(data=data)

        data = [{'op': 'replace',
                 'path': '/string_required',
                 'value': 'aaa'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=200)

        data = [{'op': 'replace_invalid',
                 'path': '/status',
                 'value': 'active'}]
        url = '/sample_artifact/%s' % art1['id']
        self.patch(url=url, data=data, status=400)


class TestLinks(base.TestArtifact):
    def test_manage_links(self):
        some_af = self.create_artifact(data={"name": "test_af"})
        dep_af = self.create_artifact(data={"name": "test_dep_af"})
        dep_url = "/artifacts/sample_artifact/%s" % some_af['id']

        # set valid link
        patch = [{"op": "replace", "path": "/link1", "value": dep_url}]
        url = '/sample_artifact/%s' % dep_af['id']
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['link1'], dep_url)

        # remove link from artifact
        patch = [{"op": "replace", "path": "/link1", "value": None}]
        af = self.patch(url=url, data=patch)
        self.assertIsNone(af['link1'])

        # try to set invalid link
        patch = [{"op": "replace", "path": "/link1", "value": "Invalid"}]
        self.patch(url=url, data=patch, status=400)

        # try to set link to non-existing artifact
        non_exiting_url = "/artifacts/sample_artifact/%s" % uuid.uuid4()
        patch = [{"op": "replace",
                  "path": "/link1",
                  "value": non_exiting_url}]
        self.patch(url=url, data=patch, status=400)

    def test_manage_dict_of_links(self):
        some_af = self.create_artifact(data={"name": "test_af"})
        dep_af = self.create_artifact(data={"name": "test_dep_af"})
        dep_url = "/artifacts/sample_artifact/%s" % some_af['id']

        # set valid link
        patch = [{"op": "add",
                  "path": "/dict_of_links/link1",
                  "value": dep_url}]
        url = '/sample_artifact/%s' % dep_af['id']
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['dict_of_links']['link1'], dep_url)

        # remove link from artifact
        patch = [{"op": "remove",
                  "path": "/dict_of_links/link1"}]
        af = self.patch(url=url, data=patch)
        self.assertNotIn('link1', af['dict_of_links'])

        # try to set invalid link
        patch = [{"op": "replace",
                  "path": "/dict_of_links/link1",
                  "value": "Invalid"}]
        self.patch(url=url, data=patch, status=400)

        # try to set link to non-existing artifact
        non_exiting_url = "/artifacts/sample_artifact/%s" % uuid.uuid4()
        patch = [{"op": "replace",
                  "path": "/dict_of_links/link1",
                  "value": non_exiting_url}]
        self.patch(url=url, data=patch, status=400)

    def test_manage_list_of_links(self):
        some_af = self.create_artifact(data={"name": "test_af"})
        dep_af = self.create_artifact(data={"name": "test_dep_af"})
        dep_url = "/artifacts/sample_artifact/%s" % some_af['id']

        # set valid link
        patch = [{"op": "add",
                  "path": "/list_of_links/-",
                  "value": dep_url}]
        url = '/sample_artifact/%s' % dep_af['id']
        af = self.patch(url=url, data=patch)
        self.assertEqual(af['list_of_links'][0], dep_url)

        # remove link from artifact
        patch = [{"op": "remove",
                  "path": "/list_of_links/0"}]
        af = self.patch(url=url, data=patch)
        self.assertEqual(0, len(af['list_of_links']))

        # try to set invalid link
        patch = [{"op": "add",
                  "path": "/list_of_links/-",
                  "value": "Invalid"}]
        self.patch(url=url, data=patch, status=400)

        # try to set link to non-existing artifact
        non_exiting_url = "/artifacts/sample_artifact/%s" % uuid.uuid4()
        patch = [{"op": "add",
                  "path": "/list_of_links/-",
                  "value": non_exiting_url}]
        self.patch(url=url, data=patch, status=400)
