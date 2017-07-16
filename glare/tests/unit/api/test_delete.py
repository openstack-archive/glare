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

import mock
from six import BytesIO

from glare.common import exception as exc
from glare.common import store_api
from glare.db import artifact_api
from glare.tests.unit import base


class TestArtifactDelete(base.BaseTestArtifactAPI):

    """Test Glare artifact deletion."""

    def setUp(self):
        super(TestArtifactDelete, self).setUp()
        values = {'name': 'ttt', 'version': '1.0'}
        self.artifact = self.controller.create(
            self.req, 'sample_artifact', values)
        # Upload data
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.artifact['id'], 'blob',
            BytesIO(b'a' * 100), 'application/octet-stream')
        # Check that data was uploaded successfully
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual(100, self.artifact['blob']['size'])
        self.assertEqual('active', self.artifact['blob']['status'])

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=store_api.delete_blob)
    def test_delete_with_data(self, mocked_delete):
        # Delete artifact and check that 'delete_blob' was called
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual(1, mocked_delete.call_count)

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=store_api.delete_blob)
    def test_delete_with_blob_dict(self, mocked_delete):
        # Upload data
        for i in range(10):
            self.controller.upload_blob(
                self.req, 'sample_artifact', self.artifact['id'],
                'dict_of_blobs/blob%d' % i,
                BytesIO(b'a' * 100), 'application/octet-stream')
        # Check that data was uploaded successfully
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        for i in range(10):
            self.assertEqual(
                100,
                self.artifact['dict_of_blobs']['blob%d' % i]['size'])
            self.assertEqual(
                'active',
                self.artifact['dict_of_blobs']['blob%d' % i]['status'])
        # Delete artifact and check that 'delete_blob' was called for each blob
        # 10 times for blob dict elements and once for 'blob'
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual(11, mocked_delete.call_count)

    def test_delete_not_found(self):
        self.assertRaises(exc.NotFound, self.controller.delete,
                          self.req, 'sample_artifact', 'INVALID_ID')

    def test_delete_saving_blob(self):
        blob = self.artifact['blob']
        # Change status of the blob to 'saving'
        blob['status'] = 'saving'
        artifact_api.ArtifactAPI().update_blob(
            self.req.context, self.artifact['id'], {'blob': blob})
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        blob = self.artifact['blob']
        self.assertEqual(100, blob['size'])
        self.assertEqual('saving', blob['status'])
        # Deleting of the artifact leads to Conflict error
        self.assertRaises(exc.Conflict, self.controller.delete,
                          self.req, 'sample_artifact', self.artifact['id'])
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual('drafted', self.artifact['status'])

    def test_delete_deleted_artifact(self):
        # Change status of the artifact to 'deleted'
        artifact_api.ArtifactAPI().save(
            self.req.context, self.artifact['id'], {'status': 'deleted'})
        # Delete should work properly
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=exc.NotFound)
    def test_delete_link_not_exist(self, mocked_delete):
        # Delete artifact and check that 'delete_blob' was called
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual(1, mocked_delete.call_count)

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=exc.Forbidden)
    def test_no_delete_permission(self, mocked_delete):
        # Try to delete artifact
        self.assertRaises(exc.Forbidden, self.controller.delete,
                          self.req, 'sample_artifact', self.artifact['id'])

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=exc.GlareException)
    def test_delete_unknown_store_exception(self, mocked_delete):
        # Try to delete artifact
        self.assertRaises(exc.GlareException, self.controller.delete,
                          self.req, 'sample_artifact', self.artifact['id'])

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=exc.NotFound)
    def test_delete_blob_not_found(self, mocked_delete):
        # Upload a file to blob dict
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.artifact['id'],
            'dict_of_blobs/blob',
            BytesIO(b'a' * 100), 'application/octet-stream')

        # Despite the exception artifact should be deleted successfully
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual(2, mocked_delete.call_count)

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=store_api.delete_blob)
    def test_delayed_delete_global(self, mocked_delete):
        # Enable delayed delete
        self.config(delayed_delete=True)
        # Delete artifact and check that 'delete_blob' was not called
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertEqual(0, mocked_delete.call_count)
        # Check that artifact status is 'deleted' and its blob is
        # 'pending_delete'
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual('deleted', self.artifact['status'])
        self.assertEqual('active', self.artifact['blob']['status'])
        # Disable delayed delete
        self.config(delayed_delete=False)
        # Delete artifact and check that 'delete_blob' was called this time
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertEqual(1, mocked_delete.call_count)
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])

    @mock.patch('glare.common.store_api.delete_blob',
                side_effect=store_api.delete_blob)
    def test_delayed_delete_per_artifact_type(self, mocked_delete):
        # Enable delayed delete for sample_artifact type
        # Global parameter is disabled
        self.config(delayed_delete=True,
                    group='artifact_type:sample_artifact')
        # Delete artifact and check that 'delete_blob' was not called
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertEqual(0, mocked_delete.call_count)
        # Check that artifact status is 'deleted' and its blob is
        # 'pending_delete'
        self.artifact = self.controller.show(
            self.req, 'sample_artifact', self.artifact['id'])
        self.assertEqual('deleted', self.artifact['status'])
        self.assertEqual('active', self.artifact['blob']['status'])
        # Disable delayed delete
        self.config(delayed_delete=False,
                    group='artifact_type:sample_artifact')
        # Delete artifact and check that 'delete_blob' was called this time
        self.controller.delete(self.req, 'sample_artifact',
                               self.artifact['id'])
        self.assertEqual(1, mocked_delete.call_count)
        self.assertRaises(exc.NotFound, self.controller.show,
                          self.req, 'sample_artifact', self.artifact['id'])
