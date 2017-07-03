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

        # Re-uploading blob leads to Conflict error
        self.assertRaises(
            exc.Conflict, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')

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
        self.config(enabled_artifact_types=['sample_artifact'])
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

    def test_existing_blob_dict_key(self):
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb', BytesIO(b'aaa'), 'application/octet-stream')
        artifact = self.controller.show(self.req, 'sample_artifact',
                                        self.sample_artifact['id'])
        self.assertEqual(3, artifact['dict_of_blobs']['blb']['size'])
        self.assertEqual('active', artifact['dict_of_blobs']['blb']['status'])

        # If blob key already exists Glare return Conflict error
        self.assertRaises(
            exc.Conflict, self.controller.upload_blob,
            self.req, 'sample_artifact', self.sample_artifact['id'],
            'dict_of_blobs/blb', BytesIO(b'aaa'), 'application/octet-stream')

    def test_blob_dict_storage_error(self):
        self.config(enabled_artifact_types=['sample_artifact'])
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

    @mock.patch('os.remove')
    def test_upload_with_hook(self, mocked_os_remove):
        with mock.patch.object(
                sample_artifact.SampleArtifact, 'validate_upload',
                return_value=(BytesIO(b'aaa'), 'temporary_path')):
            self.controller.upload_blob(
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'blob', BytesIO(b'aaa'), 'application/octet-stream')
            artifact = self.controller.show(self.req, 'sample_artifact',
                                            self.sample_artifact['id'])
            self.assertEqual(3, artifact['blob']['size'])
            self.assertEqual('active', artifact['blob']['status'])
            # If temporary folder has been created it must be removed
            mocked_os_remove.assert_called_once_with('temporary_path')

    @mock.patch('os.remove')
    def test_upload_with_hook_error(self, mocked_os_remove):
        with mock.patch.object(
                sample_artifact.SampleArtifact, 'validate_upload',
                side_effect=Exception):
            self.assertRaises(
                exc.BadRequest, self.controller.upload_blob,
                self.req, 'sample_artifact', self.sample_artifact['id'],
                'dict_of_blobs/blb', BytesIO(b'aaa'),
                'application/octet-stream')
            art = self.controller.show(self.req, 'sample_artifact',
                                       self.sample_artifact['id'])
            self.assertEqual({}, art['dict_of_blobs'])
            self.assertEqual(0, mocked_os_remove.call_count)

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
