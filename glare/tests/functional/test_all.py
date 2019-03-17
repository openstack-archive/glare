# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from glare.tests.functional import base


class TestAll(base.TestArtifact):

    def test_all(self):
        for type_name in self.enabled_types:
            if type_name == 'all':
                continue
            for i in range(3):
                for j in range(3):
                    self.create_artifact(
                        data={'name': '%s_%d' % (type_name, i),
                              'version': '%d' % j,
                              'tags': ['tag%s' % i]},
                        type_name=type_name)

        # get all possible artifacts
        url = '/all?sort=name:asc&limit=100'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(54, len(res))

        # get artifacts with latest versions
        url = '/all?version=latest&sort=name:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertEqual('2.0.0', art['version'])

        # get images only
        url = '/all?type_name=images&sort=name:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(9, len(res))
        for art in res:
            self.assertEqual('images', art['type_name'])

        # get images and heat_templates
        url = '/all?type_name=in:images,heat_templates&sort=name:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertIn(art['type_name'], ('images', 'heat_templates'))

        # get all artifacts sorted by type_name
        url = '/all?sort=type_name:asc&limit=100'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(54, len(res))
        self.assertEqual(sorted(res, key=lambda x: x['type_name']), res)

        # get all artifacts Sorted in Asc order based on display_type_name
        url = '/all?sort=display_type_name:asc&limit=100'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(54, len(res))
        self.assertEqual(sorted(res, key=lambda x: x['display_type_name']),
                         res)

        # get all artifacts sorted in desc order based on display_type_name
        url = '/all?sort=display_type_name:desc&limit=100'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(54, len(res))
        self.assertEqual(sorted(res, key=lambda x: x['display_type_name'],
                                reverse=True), res)

        # get Heat Template like only
        url = '/all?display_type_name=like:Heat%&sort=display_type_name:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertEqual('Heat', art['display_type_name'][:4])

        # search artifact using like for heat_templates and heat_environments
        url = '/all?type_name=like:heat%'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertEqual('heat', art['type_name'][:4])

        # TODO(kushalagrawal): Need to Add test case for display_type_name with
        # null once https://bugs.launchpad.net/glare/+bug/1741400 is resolved

    def test_all_readonlyness(self):
        self.create_artifact(data={'name': 'all'}, type_name='all', status=403)
        art = self.create_artifact(data={'name': 'image'}, type_name='images')

        url = '/all/%s' % art['id']

        # update 'all' is forbidden
        data = [{
            "op": "replace",
            "path": "/description",
            "value": "text"
        }]
        self.patch(url=url, data=data, status=403)

        # activation is forbidden
        data = [{
            "op": "replace",
            "path": "/status",
            "value": "active"
        }]
        self.patch(url=url, data=data, status=403)

        # publishing is forbidden
        data = [{
            "op": "replace",
            "path": "/visibility",
            "value": "public"
        }]
        self.patch(url=url, data=data, status=403)

        # get is okay
        new_art = self.get(url=url)
        self.assertEqual(new_art['id'], art['id'])

    def test_format_all(self):
        # Test that we used right output formatting for each type
        art1 = self.create_artifact(data={'name': 'aaa'})
        # Sample artifact adds metadata that contains its name in upper case
        self.assertEqual('AAA', art1['__some_meta_information__'])

        # 'Image' doesn't
        art2 = self.create_artifact(
            data={'name': 'aaa'},
            type_name='images')
        self.assertEqual('aaa', art2['name'])

        # fetch all artifacts
        url = '/all?sort=created_at:asc'
        res = self.get(url=url, status=200)['artifacts']
        self.assertEqual(2, len(res))

        self.assertEqual('sample_artifact', res[0]['type_name'])
        self.assertEqual('AAA', res[0]['__some_meta_information__'])

        self.assertEqual('images', res[1]['type_name'])
        self.assertNotIn('__some_meta_information__', res[1])

        # fetch artifacts by id
        url = '/all/%s' % art1['id']
        res = self.get(url=url, status=200)
        self.assertEqual('sample_artifact', res['type_name'])
        self.assertEqual('AAA', res['__some_meta_information__'])

        url = '/all/%s' % art2['id']
        res = self.get(url=url, status=200)
        self.assertEqual('images', res['type_name'])
        self.assertNotIn('__some_meta_information__', res)
