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

from oslo_versionedobjects import fields

from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators
from glare.tests.unit import base


class TestValidators(base.BaseTestArtifactAPI):

    """Class for testing field validators."""

    def test_uuid(self):
        # test if applied string is uuid4
        validator = validators.UUID()

        # valid string - no exception
        validator('167f8083-6bef-4f37-bf04-250343a2d53c')

        # invalid string - ValueError
        self.assertRaises(ValueError, validator, 'INVALID')

        # only strings can be applied as values
        self.assertEqual((fields.StringField,),
                         validators.UUID.get_allowed_types())

        self.assertEqual(
            {'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F])'
                         '{4}-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$')},
            validator.to_jsonschema())

    def test_regex(self):
        # test regex '^([0-9a-fA-F]){8}$'
        validator = validators.Regex('^([0-9a-fA-F]){8}$')

        # valid string - no exception
        validator('167f8083')

        # invalid string - ValueError
        self.assertRaises(ValueError, validator, 'INVALID')
        self.assertRaises(ValueError, validator, '167f808Z')
        self.assertRaises(ValueError, validator, '167f80835')

        # only strings can be applied as values
        self.assertEqual((fields.StringField,),
                         validators.UUID.get_allowed_types())

        self.assertEqual(
            {'pattern': '^([0-9a-fA-F]){8}$'},
            validator.to_jsonschema())

    def test_allowed_values(self):
        # test that field may have preoccupied values
        validator_s = validators.AllowedValues(['aaa', 'bbb'])
        validator_i = validators.AllowedValues([1, 2, 3])
        validator_f = validators.AllowedValues([1.0, 2.0, 3.0])

        # allowed value - no exception
        validator_s('aaa')
        validator_s('bbb')
        validator_i(1)
        validator_i(3)
        validator_f(1.0)
        validator_f(3.0)

        # not allowed value - value error
        self.assertRaises(ValueError, validator_s, 'a')
        self.assertRaises(ValueError, validator_i, 4)
        self.assertRaises(ValueError, validator_f, 4.0)

        # only strings, integers and floats can be applied as values
        self.assertEqual(
            (fields.StringField, fields.IntegerField, fields.FloatField),
            validators.AllowedValues.get_allowed_types())

        self.assertEqual({'enum': ['aaa', 'bbb']}, validator_s.to_jsonschema())
        self.assertEqual({'enum': [1, 2, 3]}, validator_i.to_jsonschema())
        self.assertEqual({'enum': [1.0, 2.0, 3.0]},
                         validator_f.to_jsonschema())

    def test_max_str_len(self):
        # test max allowed string length
        validator = validators.MaxStrLen(10)

        # allowed length - no exception
        validator('a' * 10)
        validator('')

        # too long string - value error
        self.assertRaises(ValueError, validator, 'a' * 11)

        # only strings can be applied as values
        self.assertEqual((fields.StringField,),
                         validators.MaxStrLen.get_allowed_types())

        self.assertEqual({'maxLength': 10}, validator.to_jsonschema())

    def test_min_str_len(self):
        # test min allowed string length
        validator = validators.MinStrLen(10)

        # allowed length - no exception
        validator('a' * 10)

        # too short string - value error
        self.assertRaises(ValueError, validator, 'a' * 9)
        self.assertRaises(ValueError, validator, '')

        # only strings can be applied as values
        self.assertEqual((fields.StringField,),
                         validators.MinStrLen.get_allowed_types())

        self.assertEqual({'minLength': 10}, validator.to_jsonschema())

    def test_forbidden_chars(self):
        # test that string has no forbidden chars
        validator = validators.ForbiddenChars(['a', '?'])

        # allowed length - no exception
        validator('b' * 10)

        # string contains forbidden chars - value error
        self.assertRaises(ValueError, validator, 'abc')
        self.assertRaises(ValueError, validator, '?')

        # only strings can be applied as values
        self.assertEqual((fields.StringField,),
                         validators.ForbiddenChars.get_allowed_types())

        self.assertEqual({'pattern': '^[^a?]+$'}, validator.to_jsonschema())

    def test_max_dict_size(self):
        # test max dict size
        validator = validators.MaxDictSize(3)

        # allowed size - no exception
        validator({'a': 1, 'b': 2, 'c': 3})
        validator({})

        # too big dictionary - value error
        self.assertRaises(ValueError, validator,
                          {'a': 1, 'b': 2, 'c': 3, 'd': 4})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.MaxDictSize.get_allowed_types())

        self.assertEqual({'maxProperties': 3}, validator.to_jsonschema())

    def test_min_dict_size(self):
        # test min dict size
        validator = validators.MinDictSize(3)

        # allowed size - no exception
        validator({'a': 1, 'b': 2, 'c': 3})

        # too small dictionary - value error
        self.assertRaises(ValueError, validator,
                          {'a': 1, 'b': 2})
        self.assertRaises(ValueError, validator, {})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.MinDictSize.get_allowed_types())

        self.assertEqual({'minProperties': 3}, validator.to_jsonschema())

    def test_max_list_size(self):
        # test max list size
        validator = validators.MaxListSize(3)

        # allowed size - no exception
        validator(['a', 'b', 'c'])
        validator([])

        # too big list - value error
        self.assertRaises(ValueError, validator,
                          ['a', 'b', 'c', 'd'])

        # only lists can be applied as values
        self.assertEqual((glare_fields.List,),
                         validators.MaxListSize.get_allowed_types())

        self.assertEqual({'maxItems': 3}, validator.to_jsonschema())

    def test_min_list_size(self):
        # test max list size
        validator = validators.MinListSize(3)

        # allowed size - no exception
        validator(['a', 'b', 'c'])

        # too small list - value error
        self.assertRaises(ValueError, validator, ['a', 'b'])
        self.assertRaises(ValueError, validator, [])

        # only lists can be applied as values
        self.assertEqual((glare_fields.List,),
                         validators.MinListSize.get_allowed_types())

        self.assertEqual({'minItems': 3}, validator.to_jsonschema())

    def test_max_number_size(self):
        # test max number size
        validator = validators.MaxNumberSize(10)

        # allowed size - no exception
        validator(10)
        validator(0)
        validator(10.0)
        validator(0.0)

        # too big number - value error
        self.assertRaises(ValueError, validator, 11)
        self.assertRaises(ValueError, validator, 10.1)

        # only integers and floats can be applied as values
        self.assertEqual((fields.IntegerField, fields.FloatField),
                         validators.MaxNumberSize.get_allowed_types())

        self.assertEqual({'maximum': 10}, validator.to_jsonschema())

    def test_min_number_size(self):
        # test min number size
        validator = validators.MinNumberSize(10)

        # allowed size - no exception
        validator(10)
        validator(10.0)

        # too small number - value error
        self.assertRaises(ValueError, validator, 9)
        self.assertRaises(ValueError, validator, 9.9)
        self.assertRaises(ValueError, validator, 0)
        self.assertRaises(ValueError, validator, 0)

        # only integers and floats can be applied as values
        self.assertEqual((fields.IntegerField, fields.FloatField),
                         validators.MinNumberSize.get_allowed_types())

        self.assertEqual({'minimum': 10}, validator.to_jsonschema())

    def test_unique(self):
        # test uniqueness of list elements

        # validator raises exception in case of duplicates in the list
        validator = validators.Unique()
        # non strict validator removes duplicates without raising of ValueError
        validator_nonstrict = validators.Unique(convert_to_set=True)

        # all elements unique - no exception
        validator(['a', 'b', 'c'])
        validator([])

        # duplicates in the list - value error
        self.assertRaises(ValueError, validator, ['a', 'a', 'b'])

        # non-strict validator converts list to set of elements
        l = ['a', 'a', 'b']
        validator_nonstrict(l)
        self.assertEqual({'a', 'b'}, set(l))

        # only lists can be applied as values
        self.assertEqual((glare_fields.List,),
                         validators.Unique.get_allowed_types())

        self.assertEqual({'uniqueItems': True}, validator.to_jsonschema())

    def test_allowed_dict_keys(self):
        # test that dictionary contains only allowed keys
        validator = validators.AllowedDictKeys(['aaa', 'bbb', 'ccc'])

        # only allowed keys - no exception
        validator({'aaa': 5, 'bbb': 6})
        validator({})

        # if dictionary has other keys - value error
        self.assertRaises(ValueError, validator, {'aaa': 5, 'a': 7, 'bbb': 6})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.AllowedDictKeys.get_allowed_types())

        self.assertEqual({'properties': {'aaa': {}, 'bbb': {}, 'ccc': {}}},
                         validator.to_jsonschema())

    def test_required_dict_keys(self):
        # test that dictionary has required keys
        validator = validators.RequiredDictKeys(['aaa', 'bbb'])

        # if dict has required keys - no exception
        validator({'aaa': 5, 'bbb': 6})
        validator({'aaa': 5, 'bbb': 6, 'ccc': 7})

        # in other case - value error
        self.assertRaises(ValueError, validator, {'aaa': 5, 'a': 7})
        self.assertRaises(ValueError, validator, {})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.RequiredDictKeys.get_allowed_types())

        self.assertEqual({'required': ['aaa', 'bbb']},
                         validator.to_jsonschema())

    def test_max_dict_key_len(self):
        # test max limit for dict key length
        validator = validators.MaxDictKeyLen(5)

        # if key length less than the limit - no exception
        validator({'aaaaa': 5, 'bbbbb': 4})

        # in other case - value error
        self.assertRaises(ValueError, validator, {'aaaaaa': 5, 'a': 7})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.MaxDictKeyLen.get_allowed_types())

    def test_mix_dict_key_len(self):
        # test min limit for dict key length
        validator = validators.MinDictKeyLen(5)

        # if key length bigger than the limit - no exception
        validator({'aaaaa': 5, 'bbbbb': 4})

        # in other case - value error
        self.assertRaises(ValueError, validator, {'aaaaa': 5, 'a': 7})

        # only dicts can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.MinDictKeyLen.get_allowed_types())

    def test_allowed_list_values(self):
        # test that list contains only allowed values
        # AllowedValues validator will be applied to each element of the list
        validator = validators.ListElementValidator(
            [validators.AllowedValues(['aaa', 'bbb', 'ccc'])])

        # only allowed values - no exception
        validator(['aaa', 'bbb'])
        validator([])

        # if list has other values - value error
        self.assertRaises(ValueError, validator, ['aaa', 'a', 'bbb'])
        self.assertRaises(ValueError, validator, ['ccc', {'aaa': 'bbb'}])

        # only lists can be applied as values
        self.assertEqual((glare_fields.List,),
                         validators.ListElementValidator.get_allowed_types())

        self.assertEqual({'itemValidators': [{'enum': ['aaa', 'bbb', 'ccc']}]},
                         validator.to_jsonschema())

    def test_allowed_dict_values(self):
        # test that dict contains only allowed values
        # AllowedValues validator will be applied to each element of the dict
        validator = validators.DictElementValidator(
            [validators.AllowedValues(['aaa', 'bbb', 'ccc'])])

        # only allowed values - no exception
        validator({'a': 'aaa', 'b': 'bbb'})
        validator({})

        # if dict has other values - value error
        self.assertRaises(ValueError, validator,
                          {'a': 'aaa', 'b': 'bbb', 'c': 'c'})

        # only dict can be applied as values
        self.assertEqual((glare_fields.Dict,),
                         validators.DictElementValidator.get_allowed_types())

        self.assertEqual(
            {'propertyValidators': [{'enum': ['aaa', 'bbb', 'ccc']}]},
            validator.to_jsonschema())
