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

from glance_store import exceptions as store_exc
import mock
from six import BytesIO

from glare.common import exception as exc
from glare.common import store_api
from glare.db import artifact_api
from glare.tests import sample_artifact
from glare.tests.unit import base


class TestArtifactUpload(base.BaseTestArtifactAPI):
    """Test blob uploading."""

    def setUp(self):
        super(TestArtifactUpload, self).setUp()
        values = {'name': 'ttt', 'version': '1.0'}
        self.sample_artifact = self.controller.create(
            self.req, 'sample_artifact', values)

    def test_upload_basic(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['blob']['size'])
        self.assertEqual('active', artifact['blob']['status'])

    def test_blob_size_too_big(self):
        # small blob size is limited by 10 bytes
        self.assertRaises(
            exc.RequestEntityTooLarge, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'small_blob', BytesIO(b'a' * 11), 'application/octet-stream')

    def test_already_uploaded(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['blob']['size'])
        self.assertEqual('active', artifact['blob']['status'])

        # Re-uploading blob
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaabb'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(5, artifact['blob']['size'])
        self.assertEqual('active', artifact['blob']['status'])

        # failed in pre_upload_hook validation and retain the existing data
        self.assertRaises(exc.GlareException, self.controller.upload_blob,
                          self.req, 'sample_artifact',
                          self.sample_artifact['id'], 'blob',
                          BytesIO(b'invalid_data'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(5, artifact['blob']['size'])
        self.assertEqual('active', artifact['blob']['status'])

    def test_upload_saving_blob(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        self.sample_artifact = self.controller.show(
            self.req, 'sample_artifact', self.sample_artifact['id'])

        # Change status of the blob to 'saving'
        self.sample_artifact['blob']['status'] = 'saving'
        artifact_api.ArtifactAPI().update_blob(
            self.req.context, self.sample_artifact['id'],
            {'blob': self.sample_artifact['blob']})
        self.sample_artifact = self.controller.show(
            self.req, 'sample_artifact', self.sample_artifact['id'])
        self.assertEqual('saving', self.sample_artifact['blob']['status'])

        # Uploading new blob leads to Conflict error
        self.assertRaises(
            exc.Conflict, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')

    def test_storage_error(self):
        self.config(default_store='filesystem',
                    group='artifact_type:sample_artifact')
        with mock.patch('glance_store.backend.add_to_backend',
                        side_effect=store_exc.GlanceStoreException):
            self.assertRaises(
                exc.GlareException, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'blob', BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertIsNone(artifact['blob'])

    def test_upload_blob_dict(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb1',
            BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['dict_of_blobs']['blb1']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['blb1']['status'])

        # upload another one
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb2',
            BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['dict_of_blobs']['blb2']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['blb2']['status'])

    def test_upload_oversized_blob_dict(self):
        # dict_of_blobs has a limit in 2000 bytes in it

        # external location shouldn't affect folder size
        ct = 'application/vnd+openstack.glare-custom-location+json'
        body = {'url': 'https://FAKE_LOCATION.com',
                'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"}
        artifact = self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/external', body, ct)
        self.assertIsNone(artifact['dict_of_blobs']['external']['size'])
        self.assertEqual('active',
                         artifact['dict_of_blobs']['external']['status'])

        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/a',
            BytesIO(1800 * b'a'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(1800, artifact['dict_of_blobs']['a']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['a']['status'])

        # upload another one
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/b',
            BytesIO(199 * b'b'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(199, artifact['dict_of_blobs']['b']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['b']['status'])

        # upload to have size of 2000 bytes exactly
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/c',
            BytesIO(b'c'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(1, artifact['dict_of_blobs']['c']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['c']['status'])

        # Upload to have more than max folder limit, more than 2000
        self.assertRaises(
            exc.RequestEntityTooLarge, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/d', BytesIO(b'd'), 'application/octet-stream')

    def test_upload_with_content_length(self):
        # dict_of_blobs has a limit in 2000 bytes in it

        # external location shouldn't affect folder size
        ct = 'application/vnd+openstack.glare-custom-location+json'
        body = {'url': 'https://FAKE_LOCATION.com',
                'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"}
        artifact = self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/external', body, ct)
        self.assertIsNone(artifact['dict_of_blobs']['external']['size'])
        self.assertEqual('active',
                         artifact['dict_of_blobs']['external']['status'])

        # Error if we provide a content length bigger than max folder size
        with mock.patch('glare.common.store_api.save_blob_to_store') as m:
            self.assertRaises(
                exc.RequestEntityTooLarge, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/d', BytesIO(b'd' * 2001),
                'application/octet-stream', content_length=2001)
            # Check that upload hasn't started
            self.assertEqual(0, m.call_count)

        # Try to cheat and provide content length lesser than we want to upload
        with mock.patch('glare.common.store_api.save_blob_to_store',
                        side_effect=store_api.save_blob_to_store) as m:
            self.assertRaises(
                exc.RequestEntityTooLarge, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/d', BytesIO(b'd' * 2001),
                'application/octet-stream', content_length=100)
            # Check that upload was called this time
            self.assertEqual(1, m.call_count)

        # Upload lesser amount of data works
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/a',
            BytesIO(b'a' * 1800), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(1800, artifact['dict_of_blobs']['a']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['a']['status'])

        # Now we have only 200 bytes left
        # Uploading of 201 byte fails immediately
        with mock.patch('glare.common.store_api.save_blob_to_store') as m:
            self.assertRaises(
                exc.RequestEntityTooLarge, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/d', BytesIO(b'd' * 201),
                'application/octet-stream', content_length=201)
            # Check that upload hasn't started
            self.assertEqual(0, m.call_count)

    def test_existing_blob_dict_key(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb', BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['dict_of_blobs']['blb']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['blb']['status'])

        # Validate re-uploaded of blob content.
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb', BytesIO(b'aaabb'),
            'application/octet-stream')

        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(5, artifact['dict_of_blobs']['blb']['size'])

    def test_blob_dict_storage_error(self):
        self.config(default_store='filesystem',
                    group='artifact_type:sample_artifact')
        with mock.patch('glance_store.backend.add_to_backend',
                        side_effect=store_exc.GlanceStoreException):
            self.assertRaises(
                exc.GlareException, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/blb', BytesIO(b'aaa'),
                'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertNotIn('blb', artifact['dict_of_blobs'])

    def test_upload_with_hook(self):
        with mock.patch.object(
                sample_artifact.SampleArtifact, 'pre_upload_hook',
                return_value=BytesIO(b'ffff')):
            self.controller.upload_blob(
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'blob', BytesIO(b'aaa'), 'application/octet-stream')
            artifact = self.controller.show(self.req, 'sample_artifact',
                                            self.sample_artifact['id'])
            self.assertEqual(4, artifact['blob']['size'])
            self.assertEqual('active', artifact['blob']['status'])

    def test_upload_with_hook_error(self):
        with mock.patch.object(
                sample_artifact.SampleArtifact, 'pre_upload_hook',
                side_effect=Exception):
            self.assertRaises(
                exc.BadRequest, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/blb', BytesIO(b'aaa'),
                'application/octet-stream')
            art = self.controller.show(self.req, 'sample_artifact',
                                       self.sample_artifact['id'])
            self.assertEqual({}, art['dict_of_blobs'])

    def test_upload_nonexistent_field(self):
        self.assertRaises(
            exc.BadRequest, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'], 'INVALID',
            BytesIO(b'aaa'), 'application/octet-stream')

        self.assertRaises(
            exc.BadRequest, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'blob/key', BytesIO(b'aaa'), 'application/octet-stream')

    def test_upload_non_blob_field(self):
        self.assertRaises(
            exc.BadRequest, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'], 'int1',
            BytesIO(b'aaa'), 'application/octet-stream')

    def test_upload_blob_dict_without_key(self):
        self.assertRaises(
            exc.BadRequest, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/', BytesIO(b'aaa'), 'application/octet-stream')

    def test_parallel_uploading_and_activation(self):
        """
        This test check whether it is possible to activate an artifact,
        when it has uploading blobs.
        """
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        self.sample_artifact = self.controller.show(
            self.req, 'sample_artifact', self.sample_artifact['id'])
        changes = [{'op': 'replace',
                    'path': '/string_required',
                    'value': 'ttt'}]
        self.update_with_values(changes)

        # Change status of the blob to 'saving'
        self.sample_artifact['blob']['status'] = 'saving'
        artifact_api.ArtifactAPI().update_blob(
            self.req.context, self.sample_artifact['id'],
            {'blob': self.sample_artifact['blob']})
        self.sample_artifact = self.controller.show(
            self.req, 'sample_artifact', self.sample_artifact['id'])
        self.assertEqual('saving', self.sample_artifact['blob']['status'])

        # activation of artifact with saving blobs lead to Conflict error
        changes = [{'op': 'replace', 'path': '/status', 'value': 'active'}]
        self.assertRaises(exc.Conflict, self.update_with_values, changes)

        # create another artifact which doesn't have uploading blobs
        values = {'name': 'ttt', 'version': '2.0', 'string_required': 'rrr'}
        new_artifact = self.controller.create(
            self.req, 'sample_artifact', values)
        # activation is possible
        res = self.update_with_values(changes, art_id=new_artifact['id'])
        self.assertEqual('active', res['status'])
