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

import tempfile

from six import BytesIO

from glare.tests.unit import base


class TestArtifactHooks(base.BaseTestArtifactAPI):

    def test_create_hook(self):
        values = {'name': 'ttt', 'version': '1.0', 'temp_dir': self.test_dir}
        art = self.controller.create(self.req, 'hooks_artifact', values)
        self.assertEqual(self.test_dir, art['temp_dir'])
        self.assertIsNotNone(art['temp_file_path_create'])
        with open(art['temp_file_path_create']) as f:
            self.assertEqual('pre_create_hook was called\n', f.readline())
            self.assertEqual('post_create_hook was called\n', f.readline())

    def test_update_ops_hook(self):
        self.req = self.get_fake_request(user=self.users['admin'])
        values = {'name': 'ttt', 'version': '1.0', 'temp_dir': self.test_dir}
        art = self.controller.create(self.req, 'hooks_artifact', values)
        self.assertEqual(self.test_dir, art['temp_dir'])

        changes = [{'op': 'replace', 'path': '/description',
                    'value': 'some_string'},
                   {'op': 'replace', 'path': '/status',
                    'value': 'active'},
                   {'op': 'replace', 'path': '/status',
                    'value': 'deactivated'},
                   {'op': 'replace', 'path': '/status',
                    'value': 'active'},
                   {'op': 'replace', 'path': '/visibility',
                    'value': 'public'}]
        art = self.update_with_values(changes, art_type='hooks_artifact',
                                      art_id=art['id'])
        self.assertEqual('active', art['status'])
        self.assertEqual('some_string', art['description'])
        self.assertEqual('public', art['visibility'])

        actions = ['update', 'activate', 'deactivate', 'reactivate', 'publish']
        for action in actions:
            with open(art['temp_file_path_%s' % action]) as f:
                self.assertEqual('pre_%s_hook was called\n' % action,
                                 f.readline())
                self.assertEqual('post_%s_hook was called\n' % action,
                                 f.readline())

    def test_upload_download_hooks(self):
        temp_file_path = tempfile.mktemp(dir=self.test_dir)
        self.config(temp_file_path=temp_file_path,
                    group='artifact_type:hooks_artifact')

        values = {'name': 'ttt', 'version': '1.0', 'temp_dir': self.test_dir}
        art = self.controller.create(self.req, 'hooks_artifact', values)

        art = self.controller.upload_blob(
            self.req, 'hooks_artifact', art['id'], 'blob',
            BytesIO(b'aaa'), 'application/octet-stream')
        self.assertEqual(3, art['blob']['size'])
        self.assertEqual('active', art['blob']['status'])

        self.controller.download_blob(
            self.req, 'hooks_artifact', art['id'], 'blob')

        with open(temp_file_path) as f:
            self.assertEqual('pre_upload_hook was called\n', f.readline())
            self.assertEqual('post_upload_hook was called\n', f.readline())
            self.assertEqual('pre_download_hook was called\n', f.readline())
            self.assertEqual('post_download_hook was called\n', f.readline())

    def test_add_location_hook(self):

        temp_file_path = tempfile.mktemp(dir=self.test_dir)
        self.config(temp_file_path=temp_file_path,
                    group='artifact_type:hooks_artifact')

        values = {'name': 'ttt', 'version': '1.0', 'temp_dir': self.test_dir}
        art = self.controller.create(self.req, 'hooks_artifact', values)

        ct = 'application/vnd+openstack.glare-custom-location+json'

        body = {'url': 'https://FAKE_LOCATION.com',
                'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"}
        art = self.controller.upload_blob(
            self.req, 'hooks_artifact', art['id'], 'blob', body, ct)
        self.assertIsNone(art['blob']['size'])
        self.assertEqual('active', art['blob']['status'])

        # hook isn't called if we download external location
        self.controller.download_blob(
            self.req, 'hooks_artifact', art['id'], 'blob')

        with open(temp_file_path) as f:
            self.assertEqual(
                'pre_add_location_hook was called\n', f.readline())
            self.assertEqual(
                'post_add_location_hook was called\n', f.readline())

    def test_delete_hook(self):
        temp_file_path = tempfile.mktemp(dir=self.test_dir)
        self.config(temp_file_path=temp_file_path,
                    group='artifact_type:hooks_artifact')

        values = {'name': 'ttt', 'version': '1.0', 'temp_dir': self.test_dir}
        art = self.controller.create(self.req, 'hooks_artifact', values)

        self.controller.delete(self.req, 'hooks_artifact', art['id'])

        with open(temp_file_path) as f:
            self.assertEqual('pre_delete_hook was called\n', f.readline())
            self.assertEqual('post_delete_hook was called\n', f.readline())
