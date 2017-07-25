# Copyright 2017 Nokia, Inc.
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
import testtools


from glare_tempest_plugin.tests.api import base
from pprint import pformat


class TestDownloadSanity(base.BaseArtifactTest):

    @testtools.testcase.attr('TestDownloadSanity')
    def test_blob_dict(self):
        """Uploading data to a folder and then download it back"""

        # Create a test artifact
        art = self.artifacts_client.create_artifact('sample_artifact',
                                                    'sample_art1')
        data = "data" * 100
        art = self.artifacts_client.upload_blob(
            'sample_artifact', art['id'], '/dict_of_blobs/new_blob', data)

        art_blob = art['dict_of_blobs']['new_blob']
        self.assertEqual(400, art_blob['size'])
        self.assertEqual('active', art_blob['status'], pformat(art_blob))

        encoded_data = data.encode('UTF-8')
        md5 = hashlib.md5(encoded_data).hexdigest()
        sha1 = hashlib.sha1(encoded_data).hexdigest()
        sha256 = hashlib.sha256(encoded_data).hexdigest()
        self.assertEqual(md5, art_blob['md5'])
        self.assertEqual(sha1, art_blob['sha1'])
        self.assertEqual(sha256, art_blob['sha256'])

        # Download data from the folder (dict_of_blobs)
        self.assertEqual(data,
                         self.artifacts_client.download_blob(
                             'sample_artifact', art['id'],
                             '/dict_of_blobs/new_blob'), pformat(art))

    @testtools.testcase.attr('TestDownloadSanity')
    def test_blob_download(self):
        data = 'some_arbitrary_testing_data'
        art = self.artifacts_client.create_artifact('sample_artifact',
                                                    'test_af')

        # upload data
        art = self.artifacts_client.upload_blob('sample_artifact',
                                                art['id'], 'blob', data)

        art_blob = art['blob']
        self.assertEqual('active', art_blob['status'], pformat(art))
        encoded_data = data.encode('UTF-8')
        md5 = hashlib.md5(encoded_data).hexdigest()
        sha1 = hashlib.sha1(encoded_data).hexdigest()
        sha256 = hashlib.sha256(encoded_data).hexdigest()
        self.assertEqual(md5, art_blob['md5'])
        self.assertEqual(sha1, art_blob['sha1'])
        self.assertEqual(sha256, art_blob['sha256'])

        #  Download data
        self.assertEqual(data,
                         self.artifacts_client.download_blob(
                             'sample_artifact', art['id'],
                             '/blob'), pformat(art))
