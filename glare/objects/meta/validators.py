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

import abc
import re
import uuid

from oslo_log import log as logging
from oslo_versionedobjects import fields
import six

from glare.common import exception
from glare.i18n import _
from glare.objects.meta import fields as glare_fields

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class Validator(object):
    """Common interface for all validators."""

    @staticmethod
    @abc.abstractmethod
    def get_allowed_types():
        raise NotImplementedError()

    def check_type_allowed(self, field_type):
        if not issubclass(field_type, self.get_allowed_types()):
            # try to check if field_type is correct
            # in case of element_type passed
            allowed_field_types = tuple(type(field.AUTO_TYPE)
                                        for field in self.get_allowed_types()
                                        if hasattr(field, 'AUTO_TYPE'))
            if not issubclass(field_type, allowed_field_types):
                raise exception.IncorrectArtifactType(
                    _("%(type)s is not allowed for validator "
                      "%(val)s. Allowed types are %(allowed)s.") % {
                        "type": str(field_type),
                        "val": str(self.__class__),
                        "allowed": str(self.get_allowed_types())})

    def to_jsonschema(self):
        return {}

    @abc.abstractmethod
    def __call__(self, value):
        raise NotImplemented


class UUID(Validator):

    @staticmethod
    def get_allowed_types():
        return fields.StringField,

    def __call__(self, value):
        uuid.UUID(value, version=4)

    def to_jsonschema(self):
        return {'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F])'
                            '{4}-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$')}


class AllowedValues(Validator):

    def __init__(self, allowed_values):
        self.allowed_values = allowed_values

    @staticmethod
    def get_allowed_types():
        return fields.StringField, fields.IntegerField, fields.FloatField

    def __call__(self, value):
        if value not in self.allowed_values:
            raise ValueError(_("Value must be one of the following: %s") %
                             ', '.join(map(str, self.allowed_values)))

    def to_jsonschema(self):
        return {'enum': self.allowed_values}


class Version(Validator):

    @staticmethod
    def get_allowed_types():
        return glare_fields.VersionField,

    def __call__(self, value):
        pass

    def to_jsonschema(self):
        return {'pattern': ('/^([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([0-9A-Za-z-]'
                            '+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+)?$/')}


class Regex(Validator):

    def __init__(self, pattern):
        self.pattern = re.compile(pattern)

    @staticmethod
    def get_allowed_types():
        return fields.StringField,

    def __call__(self, value):
        if not self.pattern.match(value):
            raise ValueError

    def to_jsonschema(self):
        return {'pattern': self.pattern.pattern}


@six.add_metaclass(abc.ABCMeta)
class SizeValidator(Validator):

    def __init__(self, size):
        self.size = size


class MaxStrLen(SizeValidator):

    @staticmethod
    def get_allowed_types():
        return fields.StringField,

    def __call__(self, value):
        l = len(value)
        if l > self.size:
            raise ValueError(
                _("String length must be less than  %(size)d. "
                  "Current length: %(cur)d") % {'size': self.size,
                                                'cur': l})

    def to_jsonschema(self):
        return {'maxLength': self.size}


class MinStrLen(SizeValidator):

    @staticmethod
    def get_allowed_types():
        return fields.StringField,

    def __call__(self, value):
        l = len(value)
        if l < self.size:
            raise ValueError(
                _("String length must be more than  %(size)d. "
                  "Current length: %(cur)d") % {'size': self.size,
                                                'cur': l})

    def to_jsonschema(self):
        return {'minLength': self.size}


class ForbiddenChars(Validator):

    def __init__(self, forbidden_chars):
        self.forbidden_chars = forbidden_chars

    @staticmethod
    def get_allowed_types():
        return fields.StringField,

    def __call__(self, value):
        for fc in self.forbidden_chars:
            if fc in value:
                raise ValueError(
                    _("Forbidden character %(char)c found in string "
                      "%(string)s")
                    % {"char": fc, "string": value})

    def to_jsonschema(self):
        return {'pattern': '^[^%s]+$' % ''.join(self.forbidden_chars)}


@six.add_metaclass(abc.ABCMeta)
class MaxSize(SizeValidator):

    def __call__(self, value):
        l = len(value)
        if l > self.size:
            raise ValueError(
                _("Number of items must be less than  "
                  "%(size)d. Current size: %(cur)d") %
                {'size': self.size, 'cur': l})


class MaxDictSize(MaxSize):

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def to_jsonschema(self):
        return {'maxProperties': self.size}


class MaxListSize(MaxSize):

    @staticmethod
    def get_allowed_types():
        return glare_fields.List,

    def to_jsonschema(self):
        return {'maxItems': self.size}


@six.add_metaclass(abc.ABCMeta)
class MinSize(SizeValidator):

    def __call__(self, value):
        l = len(value)
        if l < self.size:
            raise ValueError(
                _("Number of items must be greater than  "
                  "%(size)d. Current size: %(cur)d") %
                {'size': self.size, 'cur': l})


class MinDictSize(MinSize):

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def to_jsonschema(self):
        return {'minProperties': self.size}


class MinListSize(MinSize):

    @staticmethod
    def get_allowed_types():
        return glare_fields.List,

    def to_jsonschema(self):
        return {'minItems': self.size}


class MaxNumberSize(SizeValidator):

    def __call__(self, value):
        if value > self.size:
            raise ValueError("Number is too big: %d. Max allowed number is "
                             "%d" % (value, self.size))

    @staticmethod
    def get_allowed_types():
        return fields.IntegerField, fields.FloatField

    def to_jsonschema(self):
        return {'maximum': self.size}


class MinNumberSize(SizeValidator):

    def __call__(self, value):
        if value < self.size:
            raise ValueError("Number is too small: %d. Min allowed number is "
                             "%d" % (value, self.size))

    @staticmethod
    def get_allowed_types():
        return fields.IntegerField, fields.FloatField

    def to_jsonschema(self):
        return {'minimum': self.size}


class Unique(Validator):

    def __init__(self, convert_to_set=False):
        self.convert_to_set = convert_to_set

    @staticmethod
    def get_allowed_types():
        return glare_fields.List,

    def __call__(self, value):
        if self.convert_to_set:
            value[:] = list(set(value))
        elif len(value) != len(set(value)):
            raise ValueError(_("List items %s must be unique.") % value)

    def to_jsonschema(self):
        return {'uniqueItems': True}


class AllowedDictKeys(Validator):

    def __init__(self, allowed_keys):
        self.allowed_items = allowed_keys

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def __call__(self, value):
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

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def __call__(self, value):
        for item in self.required_items:
            if item not in value:
                raise ValueError(_("Key \"%(item)s\" is required in "
                                   "dictionary %(value)s.") %
                                 {"item": item,
                                  "value": ''.join(
                                      '{}:{}, '.format(key, val)
                                      for key, val in value.items())})

    def to_jsonschema(self):
        return {'required': list(self.required_items)}


class MaxDictKeyLen(SizeValidator):

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def __call__(self, value):
        for key in value:
            if len(str(key)) > self.size:
                raise ValueError(_("Dict key length %(key)s must be less than "
                                   "%(size)d.") % {'key': key,
                                                   'size': self.size})


class MinDictKeyLen(SizeValidator):

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def __call__(self, value):
        for key in value:
            if len(str(key)) < self.size:
                raise ValueError(_("Dict key length %(key)s must be bigger "
                                   "than %(size)d.") % {'key': key,
                                                        'size': self.size})


@six.add_metaclass(abc.ABCMeta)
class ElementValidator(Validator):

    def __init__(self, validators):
        self.validators = validators


class ListElementValidator(ElementValidator):

    @staticmethod
    def get_allowed_types():
        return glare_fields.List,

    def __call__(self, value):
        for v in value:
            for validator in self.validators:
                validator(v)

    def to_jsonschema(self):
        return {'itemValidators': [
            val.to_jsonschema() for val in self.validators
        ]}


class DictElementValidator(ElementValidator):

    @staticmethod
    def get_allowed_types():
        return glare_fields.Dict,

    def __call__(self, value):
        for v in value.values():
            for validator in self.validators:
                validator(v)

    def to_jsonschema(self):
        return {'propertyValidators': [
            val.to_jsonschema() for val in self.validators
        ]}
