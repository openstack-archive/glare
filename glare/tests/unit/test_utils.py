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

from glare.common import exception as exc
from glare.tests.unit import base

import glare.common.utils as utils


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


class TestUtilsDictDiff(base.BaseTestCase):
    """tests for utils.DictDiffer class"""
    def test_str_repr(self):
        past_dict = {"a": 1, "b": 2, "d": 4}
        current_dic = {"b": 2, "d": "different value!", "e": "new!"}
        dict_diff = utils.DictDiffer(current_dic, past_dict)
        expected_dict_str = "\nResult output:\n\tAdded keys: " \
                            "e\n\tRemoved keys:" \
                            " a\n\tChanged keys: d\n\tUnchanged keys: b\n"
        self.assertEqual(str(dict_diff), expected_dict_str)
