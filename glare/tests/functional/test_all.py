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
        res = self.get(url=url, status=200)['all']
        from pprint import pformat
        self.assertEqual(54, len(res), pformat(res))

        # get artifacts with latest versions
        url = '/all?version=latest&sort=name:asc'
        res = self.get(url=url, status=200)['all']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertEqual('2.0.0', art['version'])

        # get images only
        url = '/all?type_name=images&sort=name:asc'
        res = self.get(url=url, status=200)['all']
        self.assertEqual(9, len(res))
        for art in res:
            self.assertEqual('images', art['type_name'])

        # get images and heat_templates
        url = '/all?type_name=in:images,heat_templates&sort=name:asc'
        res = self.get(url=url, status=200)['all']
        self.assertEqual(18, len(res))
        for art in res:
            self.assertIn(art['type_name'], ('images', 'heat_templates'))

    def test_all_readonlyness(self):
        self.create_artifact(data={'name': 'all'}, type_name='all', status=403)
        art = self.create_artifact(data={'name': 'image'}, type_name='images')

        url = '/all/%s' % art['id']

        headers = {'Content-Type': 'application/octet-stream'}
        # upload to 'all' is forbidden
        self.put(url=url + '/icon', data='data', status=403,
                 headers=headers)

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
