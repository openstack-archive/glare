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

from six import BytesIO

from glare.common import exception as exc
from glare.tests.unit import base


class TestDeleteBlobs(base.BaseTestArtifactAPI):
    """Test deleting of custom locations."""

    def setUp(self):
        super(TestDeleteBlobs, self).setUp()
        values = {'name': 'ttt', 'version': '1.0', 'int1': '10'}
        self.sample_artifact = self.controller.create(
            self.req, 'sample_artifact', values)
        self.ct = 'application/vnd+openstack.glare-custom-location+json'

    def test_delete_external_blob(self):
        # Add external location
        body = {'url': 'https://FAKE_LOCATION.com',
                'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"}
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'blob', body, self.ct)
        art = self.controller.show(self.req, 'sample_artifact',
                                   self.sample_artifact['id'])
        self.assertEqual('active', art['blob']['status'])
        self.assertEqual('fake', art['blob']['md5'])
        self.assertEqual('fake_sha', art['blob']['sha1'])
        self.assertEqual('fake_sha256', art['blob']['sha256'])
        self.assertIsNone(art['blob']['size'])
        self.assertIsNone(art['blob']['content_type'])
        self.assertEqual('https://FAKE_LOCATION.com',
                         art['blob']['url'])
        self.assertNotIn('id', art['blob'])

        # Delete external blob works
        self.controller.delete_external_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob')

        art = self.controller.show(self.req, 'sample_artifact',
                                   self.sample_artifact['id'])
        self.assertIsNone(art['blob'])

    def test_delete_external_blob_dict(self):
        # Add external location to the folder
        body = {'url': 'https://FAKE_LOCATION.com',
                'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"}
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blob', body, self.ct)
        art = self.controller.show(self.req, 'sample_artifact',
                                   self.sample_artifact['id'])
        self.assertEqual('active', art['dict_of_blobs']['blob']['status'])
        self.assertEqual('fake', art['dict_of_blobs']['blob']['md5'])
        self.assertEqual('fake_sha', art['dict_of_blobs']['blob']['sha1'])
        self.assertEqual('fake_sha256',
                         art['dict_of_blobs']['blob']['sha256'])
        self.assertIsNone(art['dict_of_blobs']['blob']['size'])
        self.assertIsNone(art['dict_of_blobs']['blob']['content_type'])
        self.assertEqual('https://FAKE_LOCATION.com',
                         art['dict_of_blobs']['blob']['url'])
        self.assertNotIn('id', art['blob'])

        # Delete external blob works
        self.controller.delete_external_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blob')

        art = self.controller.show(self.req, 'sample_artifact',
                                   self.sample_artifact['id'])
        self.assertNotIn('blob', art['dict_of_blobs'])

    def test_delete_internal_blob(self):
        # Upload data to regular blob
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['blob']['size'])
        self.assertEqual('active', artifact['blob']['status'])

        # Deletion of uploaded internal blobs fails with Forbidden
        self.assertRaises(
            exc.Forbidden, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob')

    def test_delete_internal_blob_dict(self):
        # Upload data to the blob dict
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blob', BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['dict_of_blobs']['blob']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['blob']['status'])

        # Deletion of uploaded internal blobs fails with Forbidden
        self.assertRaises(
            exc.Forbidden, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blob')

    def test_delete_blob_wrong(self):
        # Non-blob field
        self.assertRaises(
            exc.BadRequest, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'int1')

        # Non-existing field
        self.assertRaises(
            exc.BadRequest, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'Nonexisting')

        # Empty blob
        self.assertRaises(
            exc.NotFound, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'blob')

        # No blob in the blob dict
        self.assertRaises(
            exc.NotFound, self.controller.delete_external_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/Nonexisting')
