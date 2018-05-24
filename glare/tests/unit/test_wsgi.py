# Copyright 2010-2011 OpenStack Foundation
# Copyright 2014 IBM Corp.
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

import datetime
import os
import socket

import eventlet.patcher
import fixtures
import mock
from oslo_concurrency import processutils
from oslo_serialization import jsonutils
import routes
import six
from six.moves import http_client as http
import webob

from glare.api.v1 import router
from glare.common import exception
from glare.common import wsgi
from glare import i18n
from glare.tests.unit import base


class RequestTest(base.BaseTestCase):

    def test_content_range(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Range"] = 'bytes 10-99/*'
        range_ = request.get_content_range()
        self.assertEqual(10, range_.start)
        self.assertEqual(100, range_.stop)  # non-inclusive
        self.assertIsNone(range_.length)

    def test_content_range_invalid(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Content-Range"] = 'bytes=0-99'
        self.assertRaises(webob.exc.HTTPBadRequest,
                          request.get_content_range)

    def test_language_accept_default(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept-Language"] = "zz-ZZ,zz;q=0.8"
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_language_accept_none(self):
        request = wsgi.Request.blank('/tests/123')
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_best_match_language_expected(self):
        # If Accept-Language is a supported language, best_match_language()
        # returns it.
        with mock.patch('babel.localedata.locale_identifiers',
                        return_value=['en']):
            req = wsgi.Request.blank('/', headers={'Accept-Language': 'en'})
        self.assertEqual('en_US', req.best_match_language())

    def test_request_match_language_unexpected(self):
        # If Accept-Language is a language we do not support,
        # best_match_language() returns None.
        with mock.patch('babel.localedata.locale_identifiers',
                        return_value=['en']):
            req = wsgi.Request.blank(
                '/', headers={'Accept-Language': 'Klingon'})
        self.assertIsNone(req.best_match_language())

    @mock.patch.object(webob.acceptparse.AcceptLanguageValidHeader,
                       'best_match')
    def test_best_match_language_unknown(self, mock_best_match):
        # Test that we are actually invoking language negotiation by webop
        request = wsgi.Request.blank('/')
        accepted = 'unknown-lang'
        request.headers = {'Accept-Language': accepted}

        mock_best_match.return_value = None

        self.assertIsNone(request.best_match_language())

        # If Accept-Language is missing or empty, match should be None
        request.headers = {'Accept-Language': ''}
        self.assertIsNone(request.best_match_language())
        request.headers.pop('Accept-Language')
        self.assertIsNone(request.best_match_language())

    def test_http_error_response_codes(self):
        """Makes sure v1 unallowed methods return 405"""
        unallowed_methods = [
            ('/schemas', ['PUT', 'DELETE', 'HEAD', 'PATCH', 'POST']),
            ('/schemas/type_name', ['PUT', 'DELETE', 'HEAD', 'PATCH', 'POST']),
            ('/artifacts/type_name', ['PUT', 'DELETE', 'HEAD', 'PATCH']),
            ('/artifacts/type_name/artifact_id', ['PUT', 'HEAD', 'POST']),
            ('/artifacts/type_name/artifact_id/blob)name',
             ['HEAD', 'PATCH', 'POST']),
        ]
        api = router.API(routes.Mapper())
        for uri, methods in unallowed_methods:
            for method in methods:
                req = webob.Request.blank(uri)
                req.method = method
                res = req.get_response(api)
                self.assertEqual(http.METHOD_NOT_ALLOWED, res.status_int)

        # Makes sure not implemented methods return 405
        req = webob.Request.blank('/schemas/image')
        req.method = 'NonexistentMethod'
        res = req.get_response(api)
        self.assertEqual(http.METHOD_NOT_ALLOWED, res.status_int)


class ResourceTest(base.BaseTestCase):

    def test_get_action_args(self):
        env = {
            'wsgiorg.routing_args': [
                None,
                {
                    'controller': None,
                    'format': None,
                    'action': 'update',
                    'id': 12,
                },
            ],
        }

        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)

        self.assertEqual(expected, actual)

    def test_get_action_args_invalid_index(self):
        env = {'wsgiorg.routing_args': []}
        expected = {}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_get_action_args_del_controller_error(self):
        actions = {'format': None,
                   'action': 'update',
                   'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_get_action_args_del_format_error(self):
        actions = {'action': 'update', 'id': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        expected = {'action': 'update', 'id': 12}
        actual = wsgi.Resource(None, None, None).get_action_args(env)
        self.assertEqual(expected, actual)

    def test_dispatch(self):
        class Controller(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(expected, actual)

    def test_dispatch_default(self):
        class Controller(object):
            def default(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        actual = resource.dispatch(Controller(), 'index', 'on', pants='off')
        expected = ('on', 'off')
        self.assertEqual(expected, actual)

    def test_dispatch_no_default(self):
        class Controller(object):
            def show(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(None, None, None)
        self.assertRaises(AttributeError, resource.dispatch, Controller(),
                          'index', 'on', pants='off')

    def test_call(self):
        class FakeController(object):
            def index(self, shirt, pants=None):
                return shirt, pants

        resource = wsgi.Resource(FakeController(), None, None)

        def dispatch(obj, *args, **kwargs):
            if isinstance(obj, wsgi.JSONRequestDeserializer):
                return []
            if isinstance(obj, wsgi.JSONResponseSerializer):
                raise webob.exc.HTTPForbidden()

        with mock.patch('glare.common.wsgi.Resource.dispatch',
                        side_effect=dispatch):
            request = wsgi.Request.blank('/')
            response = resource.__call__(request)

        self.assertIsInstance(response, webob.exc.HTTPForbidden)
        self.assertEqual(http.FORBIDDEN, response.status_code)

    def test_call_raises_exception(self):
        class FakeController(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        resource = wsgi.Resource(FakeController(), None, None)

        with mock.patch('glare.common.wsgi.Resource.dispatch',
                        side_effect=Exception("test exception")):
            request = wsgi.Request.blank('/')
            response = resource.__call__(request)

        self.assertIsInstance(response, webob.exc.HTTPInternalServerError)
        self.assertEqual(http.INTERNAL_SERVER_ERROR, response.status_code)

    @mock.patch.object(wsgi, 'translate_exception')
    def test_resource_call_error_handle_localized(self,
                                                  mock_translate_exception):
        class Controller(object):
            def delete(self, req, identity):
                raise webob.exc.HTTPBadRequest(explanation='Not Found')

        actions = {'action': 'delete', 'identity': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        request = wsgi.Request.blank('/tests/123', environ=env)
        message_es = 'No Encontrado'

        resource = wsgi.Resource(Controller(),
                                 wsgi.JSONRequestDeserializer(),
                                 None)
        translated_exc = webob.exc.HTTPBadRequest(message_es)
        mock_translate_exception.return_value = translated_exc

        e = self.assertRaises(webob.exc.HTTPBadRequest,
                              resource, request)
        self.assertEqual(message_es, str(e))

    @mock.patch.object(webob.acceptparse.AcceptLanguageValidHeader,
                       'best_match')
    @mock.patch.object(i18n, 'translate')
    def test_translate_exception(self, mock_translate, mock_best_match):

        mock_translate.return_value = 'No Encontrado'
        mock_best_match.return_value = 'de'

        req = wsgi.Request.blank('/tests/123')
        req.headers["Accept-Language"] = "de"

        e = webob.exc.HTTPNotFound(explanation='Not Found')
        e = wsgi.translate_exception(req, e)
        self.assertEqual('No Encontrado', e.explanation)

    def test_response_headers_encoded(self):
        # prepare environment
        for_openstack_comrades =  \
            u'\u0417\u0430 \u043e\u043f\u0435\u043d\u0441\u0442\u0435\u043a, ' \
            u'\u0442\u043e\u0432\u0430\u0440\u0438\u0449\u0438'

        class FakeController(object):
            def index(self, shirt, pants=None):
                return (shirt, pants)

        class FakeSerializer(object):
            def index(self, response, result):
                response.headers['unicode_test'] = for_openstack_comrades

        # make request
        resource = wsgi.Resource(FakeController(), None, FakeSerializer())
        actions = {'action': 'index'}
        env = {'wsgiorg.routing_args': [None, actions]}
        request = wsgi.Request.blank('/tests/123', environ=env)
        response = resource.__call__(request)

        # ensure it has been encoded correctly
        value = (response.headers['unicode_test'].decode('utf-8')
                 if six.PY2 else response.headers['unicode_test'])
        self.assertEqual(for_openstack_comrades, value)


class JSONResponseSerializerTest(base.BaseTestCase):

    def test_to_json(self):
        fixture = {"key": "value"}
        expected = b'{"key": "value"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_to_json_with_date_format_value(self):
        fixture = {"date": datetime.datetime(1901, 3, 8, 2)}
        expected = b'{"date": "1901-03-08T02:00:00.000000"}'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_to_json_with_more_deep_format(self):
        fixture = {"is_public": True, "name": [{"name1": "test"}]}
        expected = {"is_public": True, "name": [{"name1": "test"}]}
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        actual = jsonutils.loads(actual)
        for k in expected:
            self.assertEqual(expected[k], actual[k])

    def test_to_json_with_set(self):
        fixture = set(["foo"])
        expected = b'["foo"]'
        actual = wsgi.JSONResponseSerializer().to_json(fixture)
        self.assertEqual(expected, actual)

    def test_default(self):
        fixture = {"key": "value"}
        response = webob.Response()
        wsgi.JSONResponseSerializer().default(response, fixture)
        self.assertEqual(http.OK, response.status_int)
        content_types = [h for h in response.headerlist
                         if h[0] == 'Content-Type']
        self.assertEqual(1, len(content_types))
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(b'{"key": "value"}', response.body)


class JSONRequestDeserializerTest(base.BaseTestCase):

    def test_has_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        request.headers.pop('Content-Length')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_zero_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        request.headers['Content-Length'] = 0
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_has_body_has_content_length(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'asdf'
        self.assertIn('Content-Length', request.headers)
        self.assertTrue(wsgi.JSONRequestDeserializer().has_body(request))

    def test_no_body_no_content_length(self):
        request = wsgi.Request.blank('/')
        self.assertFalse(wsgi.JSONRequestDeserializer().has_body(request))

    def test_from_json(self):
        fixture = '{"key": "value"}'
        expected = {"key": "value"}
        actual = wsgi.JSONRequestDeserializer().from_json(fixture)
        self.assertEqual(expected, actual)

    def test_from_json_malformed(self):
        fixture = 'kjasdklfjsklajf'
        self.assertRaises(webob.exc.HTTPBadRequest,
                          wsgi.JSONRequestDeserializer().from_json, fixture)

    def test_default_no_body(self):
        request = wsgi.Request.blank('/')
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {}
        self.assertEqual(expected, actual)

    def test_default_with_body(self):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        request.body = b'{"key": "value"}'
        actual = wsgi.JSONRequestDeserializer().default(request)
        expected = {"body": {"key": "value"}}
        self.assertEqual(expected, actual)

    def test_has_body_has_transfer_encoding(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked'))

    def test_has_body_multiple_transfer_encoding(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked, gzip'))

    def test_has_body_invalid_transfer_encoding(self):
        self.assertFalse(self._check_transfer_encoding(
                         transfer_encoding='invalid', content_length=0))

    def test_has_body_invalid_transfer_encoding_no_content_len_and_body(self):
        self.assertFalse(self._check_transfer_encoding(
                         transfer_encoding='invalid', include_body=False))

    def test_has_body_invalid_transfer_encoding_no_content_len_but_body(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='invalid', include_body=True))

    def test_has_body_invalid_transfer_encoding_with_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='invalid', content_length=5))

    def test_has_body_valid_transfer_encoding_with_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked', content_length=1))

    def test_has_body_valid_transfer_encoding_without_content_length(self):
        self.assertTrue(self._check_transfer_encoding(
                        transfer_encoding='chunked'))

    def _check_transfer_encoding(self, transfer_encoding=None,
                                 content_length=None, include_body=True):
        request = wsgi.Request.blank('/')
        request.method = 'POST'
        if include_body:
            request.body = b'fake_body'
        request.headers['transfer-encoding'] = transfer_encoding
        if content_length is not None:
            request.headers['content-length'] = content_length

        return wsgi.JSONRequestDeserializer().has_body(request)

    def test_get_bind_addr_default_value(self):
        expected = ('0.0.0.0', '123456')
        actual = wsgi.get_bind_addr(default_port="123456")
        self.assertEqual(expected, actual)


class ServerTest(base.BaseTestCase):
    def test_create_pool(self):
        """Ensure the wsgi thread pool is an eventlet.greenpool.GreenPool."""
        actual = wsgi.Server(threads=1).create_pool()
        self.assertIsInstance(actual, eventlet.greenpool.GreenPool)

    @mock.patch.object(wsgi.Server, 'configure_socket')
    def test_http_keepalive(self, mock_configure_socket):
        self.config(http_keepalive=False)
        self.config(workers=None)

        server = wsgi.Server(threads=1)
        server.sock = 'fake_socket'
        # mocking eventlet.wsgi server method to check it is called with
        # configured 'http_keepalive' value.
        with mock.patch.object(eventlet.wsgi,
                               'server') as mock_server:
            fake_application = "fake-application"
            server.start(fake_application, 0)
            server.wait()
            mock_server.assert_called_once_with('fake_socket',
                                                fake_application,
                                                log=server._logger,
                                                debug=False,
                                                custom_pool=server.pool,
                                                keepalive=False,
                                                socket_timeout=900)

    def test_number_of_workers(self):
        """Ensure the default number of workers matches num cpus."""
        def pid():
            i = 1
            while True:
                i += 1
                yield i

        with mock.patch.object(os, 'fork') as mock_fork:
            mock_fork.side_effect = pid
            server = wsgi.Server()
            server.configure = mock.Mock()
            fake_application = "fake-application"
            server.start(fake_application, None)
            self.assertEqual(processutils.get_worker_count(),
                             len(server.children))

    def test_set_eventlet_hub_exception(self):
        with mock.patch('eventlet.hubs.use_hub', side_effect=Exception):
            self.assertRaises(exception.WorkerCreationFailure,
                              wsgi.set_eventlet_hub)


class GetSocketTestCase(base.BaseTestCase):

    def setUp(self):
        super(GetSocketTestCase, self).setUp()
        self.useFixture(fixtures.MonkeyPatch(
            "glare.common.wsgi.get_bind_addr",
            lambda x: ('192.168.0.13', 1234)))
        addr_info_list = [(2, 1, 6, '', ('192.168.0.13', 80)),
                          (2, 2, 17, '', ('192.168.0.13', 80)),
                          (2, 3, 0, '', ('192.168.0.13', 80))]
        self.useFixture(fixtures.MonkeyPatch(
            "glare.common.wsgi.socket.getaddrinfo",
            lambda *x: addr_info_list))
        self.useFixture(fixtures.MonkeyPatch(
            "glare.common.wsgi.time.time",
            mock.Mock(side_effect=[0, 1, 5, 10, 20, 35])))
        self.useFixture(fixtures.MonkeyPatch(
            "glare.common.wsgi.utils.validate_key_cert",
            lambda *x: None))
        wsgi.CONF.cert_file = '/etc/ssl/cert'
        wsgi.CONF.key_file = '/etc/ssl/key'
        wsgi.CONF.ca_file = '/etc/ssl/ca_cert'
        wsgi.CONF.tcp_keepidle = 600

    def test_correct_configure_socket(self):
        mock_socket = mock.Mock()
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.ssl.wrap_socket',
            mock_socket))
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.eventlet.listen',
            lambda *x, **y: mock_socket))
        server = wsgi.Server()
        server.default_port = 1234
        server.configure_socket()
        self.assertIn(mock.call.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1), mock_socket.mock_calls)
        self.assertIn(mock.call.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_KEEPALIVE,
            1), mock_socket.mock_calls)
        if hasattr(socket, 'TCP_KEEPIDLE'):
            self.assertIn(mock.call().setsockopt(
                socket.IPPROTO_TCP,
                socket.TCP_KEEPIDLE,
                wsgi.CONF.tcp_keepidle), mock_socket.mock_calls)

    def test_get_socket_without_all_ssl_reqs(self):
        wsgi.CONF.key_file = None
        self.assertRaises(RuntimeError, wsgi.get_socket, 1234)

    def test_get_socket_with_bind_problems(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=(
                [wsgi.socket.error(socket.errno.EADDRINUSE)] * 3 + [None]))))
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.ssl.wrap_socket',
            lambda *x, **y: None))

        self.assertRaises(RuntimeError, wsgi.get_socket, 1234)

    def test_get_socket_with_unexpected_socket_errno(self):
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.eventlet.listen',
            mock.Mock(side_effect=wsgi.socket.error(socket.errno.ENOMEM))))
        self.useFixture(fixtures.MonkeyPatch(
            'glare.common.wsgi.ssl.wrap_socket',
            lambda *x, **y: None))
        self.assertRaises(wsgi.socket.error, wsgi.get_socket, 1234)
