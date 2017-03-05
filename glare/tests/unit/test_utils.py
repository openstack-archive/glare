# Copyright 2016 OpenStack Foundation.
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

import os
import tempfile

import mock
from OpenSSL import crypto
import six

from glare.common import exception as exc
from glare.common import utils
from glare.tests.unit import base


class TestUtils(base.BaseTestCase):
    """Test class for glare.common.utils"""

    def test_validate_quotes(self):
        self.assertIsNone(utils.validate_quotes('"classic"'))
        self.assertIsNone(utils.validate_quotes('This is a good string'))
        self.assertIsNone(utils.validate_quotes
                          ('"comma after quotation mark should work",'))
        self.assertIsNone(utils.validate_quotes
                          (',"comma before quotation mark should work"'))
        self.assertIsNone(utils.validate_quotes('"we have quotes \\" inside"'))

    def test_validate_quotes_negative(self):
        self.assertRaises(exc.InvalidParameterValue,
                          utils.validate_quotes, 'not_comma"blabla"')
        self.assertRaises(exc.InvalidParameterValue, utils.validate_quotes,
                          '"No comma after quotation mark"Not_comma')
        self.assertRaises(exc.InvalidParameterValue,
                          utils.validate_quotes, '"The quote is not closed')

    def test_no_4bytes_params(self):
        @utils.no_4byte_params
        def test_func(*args, **kwargs):
            return args, kwargs

        bad_char = u'\U0001f62a'

        # params without 4bytes unicode are okay
        args, kwargs = test_func('val1', param='val2')
        self.assertEqual(('val1',), args)
        self.assertEqual({'param': 'val2'}, kwargs)

        # test various combinations with bad param
        self.assertRaises(exc.BadRequest, test_func,
                          bad_char)
        self.assertRaises(exc.BadRequest, test_func,
                          **{bad_char: 'val1'})
        self.assertRaises(exc.BadRequest, test_func,
                          **{'param': bad_char})


class TestReaders(base.BaseTestCase):
    """Test various readers in glare.common.utils"""

    def test_cooperative_reader_iterator(self):
        """Ensure cooperative reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            for chunk in utils.CooperativeReader(tmp_fd):
                bytes_read += len(chunk)

        self.assertEqual(BYTES, bytes_read)

    def test_cooperative_reader_explicit_read(self):
        BYTES = 1024
        bytes_read = 0
        with tempfile.TemporaryFile('w+') as tmp_fd:
            tmp_fd.write('*' * BYTES)
            tmp_fd.seek(0)
            reader = utils.CooperativeReader(tmp_fd)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertEqual(BYTES, bytes_read)

    def test_cooperative_reader_no_read_method(self):
        BYTES = 1024
        stream = [b'*'] * BYTES
        reader = utils.CooperativeReader(stream)
        bytes_read = 0
        byte = reader.read()
        while len(byte) != 0:
            bytes_read += 1
            byte = reader.read()

        self.assertEqual(BYTES, bytes_read)

        # some data may be left in the buffer
        reader = utils.CooperativeReader(stream)
        reader.buffer = 'some data'
        buffer_string = reader.read()
        self.assertEqual('some data', buffer_string)

    def test_cooperative_reader_no_read_method_buffer_size(self):
        # Decrease buffer size to 1000 bytes to test its overflow
        with mock.patch('glare.common.utils.MAX_COOP_READER_BUFFER_SIZE',
                        1000):
            BYTES = 1024
            stream = [b'*'] * BYTES
            reader = utils.CooperativeReader(stream)
            # Reading 1001 bytes to the buffer leads to 413 error
            self.assertRaises(exc.RequestEntityTooLarge, reader.read, 1001)

    def test_cooperative_reader_of_iterator(self):
        """Ensure cooperative reader supports iterator backends too"""
        data = b'abcdefgh'
        data_list = [data[i:i + 1] * 3 for i in range(len(data))]
        reader = utils.CooperativeReader(data_list)
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == b'':
                break
        meat = b''.join(chunks)
        self.assertEqual(b'aaabbbcccdddeeefffggghhh', meat)

    def test_cooperative_reader_of_iterator_stop_iteration_err(self):
        """Ensure cooperative reader supports iterator backends too"""
        reader = utils.CooperativeReader([l * 3 for l in ''])
        chunks = []
        while True:
            chunks.append(reader.read(3))
            if chunks[-1] == b'':
                break
        meat = b''.join(chunks)
        self.assertEqual(b'', meat)

    def _create_generator(self, chunk_size, max_iterations):
        chars = b'abc'
        iteration = 0
        while True:
            index = iteration % len(chars)
            chunk = chars[index:index + 1] * chunk_size
            yield chunk
            iteration += 1
            if iteration >= max_iterations:
                raise StopIteration()

    def _test_reader_chunked(self, chunk_size, read_size, max_iterations=5):
        generator = self._create_generator(chunk_size, max_iterations)
        reader = utils.CooperativeReader(generator)
        result = bytearray()
        while True:
            data = reader.read(read_size)
            if len(data) == 0:
                break
            self.assertLessEqual(len(data), read_size)
            result += data
        expected = (b'a' * chunk_size +
                    b'b' * chunk_size +
                    b'c' * chunk_size +
                    b'a' * chunk_size +
                    b'b' * chunk_size)
        self.assertEqual(expected, bytes(result))

    def test_cooperative_reader_preserves_size_chunk_less_then_read(self):
        self._test_reader_chunked(43, 101)

    def test_cooperative_reader_preserves_size_chunk_equals_read(self):
        self._test_reader_chunked(1024, 1024)

    def test_cooperative_reader_preserves_size_chunk_more_then_read(self):
        chunk_size = 16 * 1024 * 1024  # 16 Mb, as in remote http source
        read_size = 8 * 1024           # 8k, as in httplib
        self._test_reader_chunked(chunk_size, read_size)

    def test_limiting_reader(self):
        """Ensure limiting reader class accesses all bytes of file"""
        BYTES = 1024
        bytes_read = 0
        data = six.BytesIO(b"*" * BYTES)
        for chunk in utils.LimitingReader(data, BYTES):
            bytes_read += len(chunk)

        self.assertEqual(BYTES, bytes_read)

        bytes_read = 0
        data = six.BytesIO(b"*" * BYTES)
        reader = utils.LimitingReader(data, BYTES)
        byte = reader.read(1)
        while len(byte) != 0:
            bytes_read += 1
            byte = reader.read(1)

        self.assertEqual(BYTES, bytes_read)

    def test_limiting_reader_fails(self):
        """Ensure limiting reader class throws exceptions if limit exceeded"""
        BYTES = 1024

        def _consume_all_iter():
            bytes_read = 0
            data = six.BytesIO(b"*" * BYTES)
            for chunk in utils.LimitingReader(data, BYTES - 1):
                bytes_read += len(chunk)

        self.assertRaises(exc.RequestEntityTooLarge, _consume_all_iter)

        def _consume_all_read():
            bytes_read = 0
            data = six.BytesIO(b"*" * BYTES)
            reader = utils.LimitingReader(data, BYTES - 1)
            byte = reader.read(1)
            while len(byte) != 0:
                bytes_read += 1
                byte = reader.read(1)

        self.assertRaises(exc.RequestEntityTooLarge, _consume_all_read)

    def test_blob_iterator(self):
        BYTES = 1024
        bytes_read = 0
        stream = [b'*'] * BYTES
        for chunk in utils.BlobIterator(stream, 64):
            bytes_read += len(chunk)

        self.assertEqual(BYTES, bytes_read)


class TestKeyCert(base.BaseTestCase):

    def test_validate_key_cert_key(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        keyfile = os.path.join(var_dir, 'privatekey.key')
        certfile = os.path.join(var_dir, 'certificate.crt')
        utils.validate_key_cert(keyfile, certfile)

    def test_validate_key_cert_no_private_key(self):
        with tempfile.NamedTemporaryFile('w+') as tmpf:
            self.assertRaises(RuntimeError,
                              utils.validate_key_cert,
                              "/not/a/file", tmpf.name)

    def test_validate_key_cert_cert_cant_read(self):
        with tempfile.NamedTemporaryFile('w+') as keyf:
            with tempfile.NamedTemporaryFile('w+') as certf:
                os.chmod(certf.name, 0)
                self.assertRaises(RuntimeError,
                                  utils.validate_key_cert,
                                  keyf.name, certf.name)

    def test_validate_key_cert_key_cant_read(self):
        with tempfile.NamedTemporaryFile('w+') as keyf:
            with tempfile.NamedTemporaryFile('w+') as certf:
                os.chmod(keyf.name, 0)
                self.assertRaises(RuntimeError,
                                  utils.validate_key_cert,
                                  keyf.name, certf.name)

    def test_validate_key_cert_key_crypto_error(self):
        var_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../', 'var'))
        keyfile = os.path.join(var_dir, 'privatekey.key')
        certfile = os.path.join(var_dir, 'certificate.crt')
        with mock.patch('OpenSSL.crypto.verify', side_effect=crypto.Error):
            self.assertRaises(RuntimeError,
                              utils.validate_key_cert,
                              keyfile, certfile)
