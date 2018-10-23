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
from time import time

from glare.common.exception import BadRequest
from glare.tests.unit import base


class TestArtifactHooks(base.BaseTestArtifactAPI):

    def setUp(self):
        super(TestArtifactHooks, self).setUp()
        values = {'name': 'ttt', 'version': '1.0'}
        self.unpacking_artifact = self.controller.create(
            self.req, 'unpacking_artifact', values)

    def test_unpacking(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        data_path = os.path.join(var_dir, 'hooks.zip')
        with open(data_path, "rb") as data:
            self.controller.upload_blob(
                self.req, 'unpacking_artifact', self.unpacking_artifact['id'],
                'zip', data, 'application/octet-stream')
        artifact = self.controller.show(self.req, 'unpacking_artifact',
                                        self.unpacking_artifact['id'])
        self.assertEqual(818, artifact['zip']['size'])
        self.assertEqual('active', artifact['zip']['status'])

        self.assertEqual(11, artifact['content']['aaa.txt']['size'])
        self.assertEqual(11, artifact['content']['folder1/bbb.txt']['size'])
        self.assertEqual(
            11, artifact['content']['folder1/folder2/ccc.txt']['size'])

    def test_unpacking_database(self):
        self.config(default_store='database',
                    group='artifact_type:unpacking_artifact')
        self.test_unpacking()

    def test_unpacking_big_archive(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        data_path = os.path.join(var_dir, 'hooks_100.zip')

        # play rally - test that this test should pass faster than 3 seconds
        start = time()
        with open(data_path, "rb") as data:
            self.controller.upload_blob(
                self.req, 'unpacking_artifact', self.unpacking_artifact['id'],
                'zip', data, 'application/octet-stream')
        end = time()
        self.assertIs(True, (end - start) < 3, (end - start))

        artifact = self.controller.show(self.req, 'unpacking_artifact',
                                        self.unpacking_artifact['id'])
        self.assertEqual(100, len(artifact['content']))
        self.assertEqual('active', artifact['zip']['status'])

        self.assertEqual(100, len(artifact['content']))

        for blob in artifact['content'].values():
            self.assertEqual('active', blob['status'])
            self.assertEqual(15, blob['size'])

    def test_unpacking_more_than_max_size_archive(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        data_path = os.path.join(var_dir, 'hooks_265.zip')
        with open(data_path, "rb") as data:
            self.assertRaises(BadRequest, self.controller.upload_blob,
                              self.req, 'unpacking_artifact',
                              self.unpacking_artifact['id'], 'zip',
                              data, 'application/octet-stream')
        artifact = self.controller.show(self.req, 'unpacking_artifact',
                                        self.unpacking_artifact['id'])
        self.assertEqual(0, len(artifact['content']))

    def test_unpacking_database_big_archive(self):
        self.config(default_store='database',
                    group='artifact_type:unpacking_artifact')
        self.test_unpacking_big_archive()
