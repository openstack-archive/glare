# Copyright 2017 OpenStack Foundation
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
import requests

from glare.tests.functional import base


class TestMultiStore(base.TestArtifact):

    def setUp(self):
        base.functional.FunctionalTest.setUp(self)

        self.set_user('user1')
        self.glare_server.deployment_flavor = 'noauth'

        self.glare_server.enabled_artifact_types = 'sample_artifact'
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')
        self.glare_server.artifact_type_section = """
[artifact_type:sample_artifact]
delayed_delete = False
default_store = database
"""
        self.start_servers(**self.__dict__.copy())

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

        self.put(url=url + '/dict_of_blobs/new_blob',
                 data=data, status=200, headers=headers)

        # Download data from blob dict
        self.assertEqual(data,
                         self.get(url=url + '/dict_of_blobs/new_blob',
                                  status=200))

        # download blob from undefined dict property
        self.get(url=url + '/not_a_dict/not_a_blob', status=400)

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
        headers = {'Content-Type': 'application/octet-stream'}

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

        # reUpload file to artifact
        self.put(url=url + '/blob', data=data, status=200,
                 headers=headers)
        # upload blob dict
        self.put(url + '/dict_of_blobs/test_key', data=data, headers=headers)
        # test re-upload for dict of blob
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
