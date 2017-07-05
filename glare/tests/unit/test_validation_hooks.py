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

import os

from glare.common import exception as exc
from glare.tests.unit import base


class TestArtifactHooks(base.BaseTestArtifactAPI):

    def setUp(self):
        super(TestArtifactHooks, self).setUp()
        values = {'name': 'ttt', 'version': '1.0'}
        self.hooks_artifact = self.controller.create(
            self.req, 'hooks_artifact', values)

    def test_upload_hook(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        data_path = os.path.join(var_dir, 'hooks.zip')
        with open(data_path, "rb") as data:
            self.controller.upload_blob(
                self.req, 'hooks_artifact', self.hooks_artifact['id'], 'zip',
                data, 'application/octet-stream')
        artifact = self.controller.show(self.req, 'hooks_artifact',
                                        self.hooks_artifact['id'])
        self.assertEqual(818, artifact['zip']['size'])
        self.assertEqual('active', artifact['zip']['status'])

        self.assertEqual(11, artifact['content']['aaa.txt']['size'])
        self.assertEqual(11, artifact['content']['folder1/bbb.txt']['size'])
        self.assertEqual(
            11, artifact['content']['folder1/folder2/ccc.txt']['size'])

    def test_download_hook(self):
        # upload data
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        data_path = os.path.join(var_dir, 'hooks.zip')
        with open(data_path, "rb") as data:
            self.controller.upload_blob(
                self.req, 'hooks_artifact', self.hooks_artifact['id'], 'zip',
                data, 'application/octet-stream')

        # download main 'zip'
        data = self.controller.download_blob(
            self.req, 'hooks_artifact', self.hooks_artifact['id'],
            'zip')['data']
        bytes_read = 0
        for chunk in data:
            bytes_read += len(chunk)
        self.assertEqual(818, bytes_read)

        # download a file from 'content'
        data = self.controller.download_blob(
            self.req, 'hooks_artifact', self.hooks_artifact['id'],
            'content/folder1/bbb.txt')['data']
        bytes_read = 0
        for chunk in data:
            bytes_read += len(chunk)
        self.assertEqual(11, bytes_read)

        # now forbid to download zip
        changes = [{'op': 'replace', 'path': '/forbid_download_zip',
                    'value': 'yes'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        artifact = self.controller.show(self.req, 'hooks_artifact',
                                        self.hooks_artifact['id'])
        self.assertEqual(True, artifact['forbid_download_zip'])

        # download from 'zip' fails now
        self.assertRaises(
            exc.BadRequest, self.controller.download_blob,
            self.req, 'hooks_artifact', self.hooks_artifact['id'], 'zip')

        # download a 'content' file still works
        data = self.controller.download_blob(
            self.req, 'hooks_artifact', self.hooks_artifact['id'],
            'content/folder1/folder2/ccc.txt')['data']
        bytes_read = 0
        for chunk in data:
            bytes_read += len(chunk)
        self.assertEqual(11, bytes_read)

    def test_activation_hook(self):
        # forbid to activate artifact
        changes = [{'op': 'replace', 'path': '/forbid_activate',
                    'value': 'yes'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # activation fails now
        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'active'}]
        self.assertRaises(
            exc.BadRequest, self.update_with_values, changes,
            art_type='hooks_artifact', art_id=self.hooks_artifact['id'])

        # unblock artifact activation
        changes = [{'op': 'replace', 'path': '/forbid_activate',
                    'value': 'no'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # now activation works
        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'active'}]
        art = self.update_with_values(changes, art_type='hooks_artifact',
                                      art_id=self.hooks_artifact['id'])
        self.assertEqual('active', art['status'])

    def test_publishing_hook(self):
        self.req = self.get_fake_request(user=self.users['admin'])

        # activate artifact to begin
        changes = [{'op': 'replace', 'path': '/status',
                    'value': 'active'}]
        art = self.update_with_values(changes, art_type='hooks_artifact',
                                      art_id=self.hooks_artifact['id'])
        self.assertEqual('active', art['status'])

        # forbid to publish artifact
        changes = [{'op': 'replace', 'path': '/forbid_publish',
                    'value': 'yes'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # publication fails now
        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': 'public'}]
        self.assertRaises(
            exc.BadRequest, self.update_with_values, changes,
            art_type='hooks_artifact', art_id=self.hooks_artifact['id'])

        # unblock artifact publication
        changes = [{'op': 'replace', 'path': '/forbid_publish',
                    'value': 'no'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # now publication works
        changes = [{'op': 'replace', 'path': '/visibility',
                    'value': 'public'}]
        art = self.update_with_values(changes, art_type='hooks_artifact',
                                      art_id=self.hooks_artifact['id'])
        self.assertEqual('public', art['visibility'])

    def test_deletion_hook(self):
        # forbid to activate artifact
        changes = [{'op': 'replace', 'path': '/forbid_delete',
                    'value': 'yes'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # deletion fails now
        self.assertRaises(
            exc.BadRequest, self.controller.delete, self.req,
            'hooks_artifact', self.hooks_artifact['id'])

        # unblock artifact deletion
        changes = [{'op': 'replace', 'path': '/forbid_delete',
                    'value': 'no'}]
        self.update_with_values(changes, art_type='hooks_artifact',
                                art_id=self.hooks_artifact['id'])

        # now deletion works
        self.controller.delete(self.req, 'hooks_artifact',
                               self.hooks_artifact['id'])
        self.assertRaises(exc.NotFound, self.controller.show, self.req,
                          'hooks_artifact', self.hooks_artifact['id'])
