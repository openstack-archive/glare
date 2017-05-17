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

from functools import partial
import inspect

import mock
from oslo_config import cfg
from oslo_log import log as logging

from glare.api.middleware import fault
from glare.common import exception as exc
from glare.tests.unit import base

CONF = cfg.CONF
logging.register_options(CONF)


class TestFaultMiddleware(base.BaseTestCase):

    @staticmethod
    def get_response(value=None, exception=Exception):
        if value is None:
            raise exception
        return value

    def _build_middleware(self):
        return fault.GlareFaultWrapperFilter(None)

    def test_no_exception(self):
        req = mock.Mock()
        req.get_response.return_value = 'Response object'
        with mock.patch.object(fault.Fault, '__init__') as mocked_fault:
            res = self._build_middleware()(req)
            self.assertEqual('Response object', res)
            self.assertEqual(0, mocked_fault.call_count)

    def test_exceptions(self):
        req = mock.Mock()
        error_map = fault.GlareFaultWrapperFilter.error_map

        # Raise all exceptions from error_map
        for name, obj in inspect.getmembers(exc, inspect.isclass):
            if not issubclass(obj, Exception)\
                    or obj is exc.InvalidGlobalAPIVersion:
                continue
            req.get_response.side_effect = partial(self.get_response,
                                                   exception=obj)
            res = self._build_middleware()(req)

            while name not in error_map:
                obj = obj.__base__
                name = obj.__name__
            self.assertEqual(error_map[name].code, res.error['code'])

        # Raise other possible exceptions that lead to 500 error
        for e in (Exception, ValueError, TypeError, exc.GlareException):
            req.get_response.side_effect = partial(
                self.get_response, exception=e)
            res = self._build_middleware()(req)
            self.assertEqual(500, res.error['code'])

        # InvalidGlobalAPIVersion should also include min_version and
        # max_version headers
        req.get_response.side_effect = partial(
            self.get_response, exception=exc.InvalidGlobalAPIVersion(
                req_ver=100.0, min_ver=1.0, max_ver=1.1))
        res = self._build_middleware()(req)
        self.assertEqual(406, res.error['code'])
        self.assertEqual(1.0, res.error['min_version'])
        self.assertEqual(1.1, res.error['max_version'])

    def test_trace_marker(self):
        req = mock.Mock()
        self.config(debug=True)
        traceback_marker = 'Traceback (most recent call last)'
        pref = "PREFIX"
        suff = "SUFFIX"

        # Test with marker
        req.get_response.side_effect = partial(
            self.get_response, exception=ValueError(
                pref + traceback_marker + suff))
        res = self._build_middleware()(req)
        self.assertEqual(500, res.error['code'])
        self.assertEqual(pref, res.error['error']['message'])
        self.assertEqual(traceback_marker + suff,
                         res.error['error']['traceback'])

        # Test without marker
        req.get_response.side_effect = partial(
            self.get_response, exception=ValueError(
                pref + suff))
        res = self._build_middleware()(req)
        self.assertEqual(500, res.error['code'])
        self.assertEqual(pref + suff, res.error['error']['message'])
        self.assertIn(traceback_marker, res.error['error']['traceback'])

    def test_fault_class(self):
        req = mock.Mock()
        req.get_response.side_effect = partial(
            self.get_response, exception=exc.BadRequest)
        res = self._build_middleware()(req)(req)
        self.assertEqual(400, res.status_code)
        self.assertEqual('400 Bad Request', res.status)
