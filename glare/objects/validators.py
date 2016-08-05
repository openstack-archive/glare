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
import uuid

from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_versionedobjects import fields

from glare.i18n import _
from glare.objects import fields as glare_fields

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
        uuid.UUID(value)


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
    def get_allowed_types(self):
        return glare_fields.Dict, glare_fields.List

    def validate(self, value):
        l = len(value)
        if l > self.size:
            raise ValueError(
                _("Number of items must be less than  "
                  "%(size)s. Current size: %(cur)s") %
                {'size': self.size, 'cur': l})


class Unique(Validator):
    def get_allowed_types(self):
        return glare_fields.List,

    def validate(self, value):
        if len(value) != len(set(value)):
            raise ValueError(_("List items %s must be unique.") % value)


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


class RequiredDictKeys(Validator):
    def __init__(self, required_keys):
        self.required_items = required_keys

    def get_allowed_types(self):
        return glare_fields.Dict,

    def validate(self, value):
        for item in self.required_items:
            if item not in value:
                raise ValueError(_("Key %(item)s is required in dict. "
                                   "Required key values: %(required)s") %
                                 {"item": item,
                                  "required": ', '.join(self.required_items)})


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
