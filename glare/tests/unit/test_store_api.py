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
import tempfile

import mock
from six import BytesIO

from glare.common import exception as exc
from glare.common import store_api
from glare.tests.unit import base
from glare.tests import utils


class TestStoreAPI(base.BaseTestArtifactAPI):

    def test_read_data_filesystem(self):
        # test local read from temp file
        tfd, path = tempfile.mkstemp()
        try:
            os.write(tfd, b'a' * 1000)
            flobj = store_api.load_from_store(
                "file://" + path,
                self.req.context
            )
            self.assertEqual(b'a' * 1000, store_api.read_data(flobj))
            flobj = store_api.load_from_store(
                "file://" + path,
                self.req.context
            )
            self.assertRaises(exc.RequestEntityTooLarge,
                              store_api.read_data, flobj, limit=999)
        finally:
            os.remove(path)

    def test_read_data_database(self):
        # test read from sql object
        values = {'name': 'ttt', 'version': '1.0'}
        self.sample_artifact = self.controller.create(
            self.req, 'sample_artifact', values)
        self.controller.upload_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob',
            BytesIO(b'a' * 100), 'application/octet-stream')
        flobj = self.controller.download_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob')
        self.assertEqual(b'a' * 100, store_api.read_data(flobj['data']))
        flobj = self.controller.download_blob(
            self.req, 'sample_artifact', self.sample_artifact['id'], 'blob')
        self.assertRaises(exc.RequestEntityTooLarge,
                          store_api.read_data, flobj['data'], limit=99)

    def test_read_data_http(self):
        request = mock.patch('requests.Session.request')
        try:
            self.request = request.start()
            self.request.return_value = utils.fake_response(
                content=b'a' * 1000)
            # test read from external http
            flobj = store_api.load_from_store(
                'http://localhost/test_file.txt',
                self.req.context
            )
            self.assertEqual(1000, len(store_api.read_data(flobj)))
        finally:
            request.stop()

    def test_read_data_http_too_large_data(self):
        request = mock.patch('requests.Session.request')
        try:
            self.request = request.start()
            self.request.return_value = utils.fake_response(
                content=b'a' * 1000)
            flobj = store_api.load_from_store(
                'http://localhost/test_file.txt',
                self.req.context
            )
            self.assertRaises(exc.RequestEntityTooLarge,
                              store_api.read_data, flobj, limit=999)
        finally:
            request.stop()
