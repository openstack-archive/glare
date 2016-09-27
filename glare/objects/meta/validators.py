# Copyright 2016 OpenStack Foundation
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

import six

from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_versionedobjects import fields

from glare.i18n import _
from glare.objects.meta import fields as glare_fields

LOG = logging.getLogger(__name__)


class Validator(object):
    """Common interface for all validators"""

    def validate(self, value):
        raise NotImplementedError()

    def get_allowed_types(self):
        raise NotImplementedError()

    def check_type_allowed(self, field_type):
        if not issubclass(field_type, self.get_allowed_types()):
            # try to check if field_type is correct
            # in case of element_type passed
            allowed_field_types = tuple(type(field.AUTO_TYPE)
                                        for field in self.get_allowed_types()
                                        if hasattr(field, 'AUTO_TYPE'))
            if not issubclass(field_type, allowed_field_types):
                raise TypeError(
                    _("%(type)s is not allowed for validator "
                      "%(val)s. Allowed types are %(allowed)s.") % {
                        "type": str(field_type),
                        "val": str(self.__class__),
                        "allowed": str(self.get_allowed_types())})

    def to_jsonschema(self):
        return {}

    def __call__(self, value):
        try:
            self.validate(value)
        except ValueError:
            raise
        except TypeError as e:
            # we are raising all expected ex Type Errors as ValueErrors
            LOG.exception(e)
            raise ValueError(encodeutils.exception_to_unicode(e))


class UUID(Validator):
    def get_allowed_types(self):
        return fields.StringField,

    def validate(self, value):
        pass

    def to_jsonschema(self):
        return {'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F])'
                            '{4}-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$')}


class AllowedValues(Validator):
    def __init__(self, allowed_values):
        self.allowed_values = allowed_values

    def get_allowed_types(self):
        return fields.StringField,

    def validate(self, value):
        if value not in self.allowed_values:
            raise ValueError(_("Value must be one of the following: %s") %
                             ', '.join(self.allowed_values))

    def to_jsonschema(self):
        return {'enum': self.allowed_values + [None]}


class Version(Validator):
    def get_allowed_types(self):
        return glare_fields.VersionField

    def validate(self, value):
        pass

    def to_jsonschema(self):
        return {'pattern': ('/^([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([0-9A-Za-z-]'
                            '+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+)?$/')}


class SizeValidator(Validator):
    def __init__(self, size):
        self.size = size


class MaxStrLen(SizeValidator):
    def get_allowed_types(self):
        return fields.StringField,

    def validate(self, value):
        l = len(value)
        if l > self.size:
            raise ValueError(
                _("String length must be less than  %(size)s. "
                  "Current size: %(cur)s") % {'size': self.size,
                                              'cur': l})

    def to_jsonschema(self):
        return {'maxLength': self.size}


class MinStrLen(SizeValidator):
    def get_allowed_types(self):
        return fields.StringField,

    def validate(self, value):
        l = len(value)
        if l < self.size:
            raise ValueError(
                _("String length must be more than  %(size)s. "
                  "Current size: %(cur)s") % {'size': self.size,
                                              'cur': l})

    def to_jsonschema(self):
        return {'minLength': self.size}


class ForbiddenChars(Validator):
    def __init__(self, forbidden_chars):
        self.forbidden_chars = forbidden_chars

    def get_allowed_types(self):
        return fields.StringField,

    def validate(self, value):
        for fc in self.forbidden_chars:
            if fc in value:
                raise ValueError(
                    _("Forbidden character %(char) found in string "
                      "%(string)s")
                    % {"char": fc, "string": value})


class MaxSize(SizeValidator):

    def validate(self, value):
        l = len(value)
        if l > self.size:
            raise ValueError(
                _("Number of items must be less than  "
                  "%(size)s. Current size: %(cur)s") %
                {'size': self.size, 'cur': l})

    def to_jsonschema(self):
        return {'maxItems': self.size}


class MaxDictSize(MaxSize):

    def get_allowed_types(self):
        return glare_fields.Dict

    def to_jsonschema(self):
        return {'maxProperties': self.size}


class MaxListSize(MaxSize):

    def get_allowed_types(self):
        return glare_fields.List

    def to_jsonschema(self):
        return {'maxItems': self.size}


class MaxNumberSize(SizeValidator):
    def validate(self, value):
        if value > self.size:
            raise ValueError("Number is too big: %s. Max allowed number is "
                             "%s" % (value, self.size))

    def get_allowed_types(self):
        return fields.IntegerField, fields.FloatField

    def to_jsonschema(self):
        return {'maximum': self.size}


class MinNumberSize(SizeValidator):
    def validate(self, value):
        if value < self.size:
            raise ValueError("Number is too small: %s. Min allowed number is "
                             "%s" % (value, self.size))

    def get_allowed_types(self):
        return fields.IntegerField, fields.FloatField

    def to_jsonschema(self):
        return {'minimum': self.size}


class Unique(Validator):
    def get_allowed_types(self):
        return glare_fields.List,

    def validate(self, value):
        if len(value) != len(set(value)):
            raise ValueError(_("List items %s must be unique.") % value)

    def to_jsonschema(self):
        return {'unique': True}


class AllowedListValues(Validator):
    def __init__(self, allowed_values):
        self.allowed_items = allowed_values

    def get_allowed_types(self):
        return glare_fields.List,

    def validate(self, value):
        for item in value:
            if item not in self.allowed_items:
                raise ValueError(
                    _("Value %(item)s is not allowed in list. "
                      "Allowed list values: %(allowed)s") %
                    {"item": item,
                     "allowed": self.allowed_items})

    def to_jsonschema(self):
        return {'enum': self.allowed_items}


class AllowedDictKeys(Validator):
    def __init__(self, allowed_keys):
        self.allowed_items = allowed_keys

    def get_allowed_types(self):
        return glare_fields.Dict,

    def validate(self, value):
        for item in value:
            if item not in self.allowed_items:
                raise ValueError(_("Key %(item)s is not allowed in dict. "
                                   "Allowed key values: %(allowed)s") %
                                 {"item": item,
                                  "allowed": ', '.join(self.allowed_items)})

    def to_jsonschema(self):
        return {
            'properties': {prop: {} for prop in self.allowed_items},
        }


class RequiredDictKeys(Validator):
    def __init__(self, required_keys):
        self.required_items = required_keys

    def get_allowed_types(self):
        return glare_fields.Dict,

    def validate(self, value):
        for item in self.required_items:
            if item not in value:
                raise ValueError(_("Key \"%(item)s\" is required in property "
                                   "dictionary: %(value)s.") %
                                 {"item": item,
                                  "value": ''.join(
                                      '{}:{}, '.format(key, val)
                                      for key, val in six.iteritems(value))})

    def to_jsonschema(self):
        return {'required': list(self.required_items)}


class MaxDictKeyLen(SizeValidator):
    def get_allowed_types(self):
        return glare_fields.Dict,

    def validate(self, value):
        for key in value:
            if len(str(key)) > self.size:
                raise ValueError(_("Dict key length %(key)s must be less than "
                                   "%(size)s.") % {'key': key,
                                                   'size': self.size})


class ElementValidator(Validator):
    def __init__(self, validators):
        self.validators = validators


class ListElementValidator(ElementValidator):
    def get_allowed_types(self):
        return glare_fields.List,

    def validate(self, value):
        for v in value:
            for validator in self.validators:
                validator(v)


class DictElementValidator(ElementValidator):
    def get_allowed_types(self):
        return glare_fields.Dict,

    def validate(self, value):
        for v in six.itervalues(value):
            for validator in self.validators:
                validator(v)
