# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""This file contains classes that wrap nat"""

from oslo_versionedobjects import fields

from glare.common import exception as exc
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators as val_lib

FILTERS = (
    FILTER_EQ, FILTER_NEQ, FILTER_IN, FILTER_GT, FILTER_GTE, FILTER_LT,
    FILTER_LTE, FILTER_LIKE) = ('eq', 'neq', 'in', 'gt', 'gte', 'lt', 'lte',
                                'like')

DEFAULT_MAX_BLOB_SIZE = 10485760  # 10 Megabytes
DEFAULT_MAX_FOLDER_SIZE = 2673868800  # 2550 Megabytes


class Field(object):
    def __init__(self, field_class, mutable=False, required_on_activate=True,
                 system=False, validators=None, nullable=True, default=None,
                 sortable=False, filter_ops=None, description="",
                 metadata=None):
        """Init and validate field.
        Each artifact field has several common properties:

        :param required_on_activate: boolean value indicating if the field
         value should be specified for the artifact
         before activation (Default:True).
        :param mutable: boolean value indicating if the field value may
         be changed after the artifact is activated. (Default: False)
        :param system: boolean value indicating if the field
         value cannot be edited by user (Default: False).
        :param sortable: boolean value indicating if there is a possibility
         to sort by this fields's values. (Default: False) Only fields of
         4 primitive types may be sortable: integer, string, float and boolean.
        :param default: a default value for the field may be specified
         (Default: None).
        :param validators: a list of objects. When user sets a value to
         the field with additional validators Glare checks them before setting
         the value and raises ValueError if at least one of the requirements
         is not satisfied.
        :param filter_ops: a list of available filter operators for the field.
         There are seven available operators:
         'eq', 'neq', 'lt', 'lte', 'gt', 'gte', 'in'.
         """

        if not issubclass(field_class, fields.AutoTypedField):
            raise exc.IncorrectArtifactType(
                "Field class %s must be sub-class of AutoTypedField." %
                field_class)

        self.validators = validators or []
        for v in self.validators:
            v.check_type_allowed(field_class)
            if isinstance(v, val_lib.MaxStrLen):
                if v.size > 255 and sortable:
                    raise exc.IncorrectArtifactType(
                        "It's forbidden to make field %(field)s "
                        "sortable if string length can be more than 255 "
                        "symbols. Maximal allowed length now: %(max)d" %
                        {"field": str(field_class), 'max': v.size})

        self.field_class = field_class
        self.nullable = nullable
        self.default = default
        self.vo_props = ['nullable', 'default']

        self.mutable = mutable
        self.required_on_activate = required_on_activate
        self.system = system
        self.sortable = sortable
        self.metadata = metadata

        try:
            default_ops = self.get_default_filter_ops(self.element_type)
            allowed_ops = self.get_allowed_filter_ops(self.element_type)
        except AttributeError:
            default_ops = self.get_default_filter_ops(field_class)
            allowed_ops = self.get_allowed_filter_ops(self.field_class)

        if filter_ops is None:
            self.filter_ops = default_ops
        else:
            for op in filter_ops:
                if op not in allowed_ops:
                    raise exc.IncorrectArtifactType(
                        "Incorrect filter operator '%s'. "
                        "Only %s are allowed" % (op, ', '.join(default_ops)))
            self.filter_ops = filter_ops

        self.field_props = ['mutable', 'required_on_activate', 'system',
                            'sortable', 'filter_ops', 'description',
                            'metadata']
        self.description = description

    @staticmethod
    def get_allowed_filter_ops(field):
        if field in (fields.StringField, fields.String):
            return [FILTER_EQ, FILTER_NEQ, FILTER_IN, FILTER_LIKE]
        elif field in (fields.IntegerField, fields.Integer, fields.FloatField,
                       fields.Float, glare_fields.VersionField):
            return FILTERS
        elif field in (fields.FlexibleBooleanField, fields.FlexibleBoolean,
                       glare_fields.Link, glare_fields.LinkFieldType):
            return [FILTER_EQ, FILTER_NEQ]
        elif field in (glare_fields.BlobField, glare_fields.BlobFieldType):
            return []
        elif field is fields.DateTimeField:
            return [FILTER_LT, FILTER_GT]

    @staticmethod
    def get_default_filter_ops(field):
        if field in (fields.StringField, fields.String):
            return [FILTER_EQ, FILTER_NEQ, FILTER_IN]
        elif field in (fields.IntegerField, fields.Integer, fields.FloatField,
                       fields.Float, glare_fields.VersionField):
            return [FILTER_EQ, FILTER_NEQ, FILTER_IN, FILTER_GT, FILTER_GTE,
                    FILTER_LT, FILTER_LTE]
        elif field in (fields.FlexibleBooleanField, fields.FlexibleBoolean,
                       glare_fields.Link, glare_fields.LinkFieldType):
            return [FILTER_EQ, FILTER_NEQ]
        elif field in (glare_fields.BlobField, glare_fields.BlobFieldType):
            return []
        elif field is fields.DateTimeField:
            return [FILTER_LT, FILTER_GT]

    def get_default_validators(self):
        default = []
        if issubclass(self.field_class, fields.StringField):
            # check if fields is string
            if not any(isinstance(v, val_lib.MaxStrLen)
                       for v in self.validators) and \
                    not any(isinstance(v, val_lib.AllowedValues)
                            for v in self.validators):
                default.append(val_lib.MaxStrLen(255))
        return default

    def get_field(self):
        # init the field
        vo_props = {prop_name: getattr(self, prop_name)
                    for prop_name in self.vo_props}
        field = self.field_class(**vo_props)
        # setup custom field properties
        field_props = {prop_name: getattr(self, prop_name)
                       for prop_name in self.field_props}
        for prop, value in field_props.items():
                setattr(field, prop, value)

        # apply custom validators
        vals = self.validators
        for def_val in self.get_default_validators():
            for val in self.validators:
                if type(val) is type(def_val):
                    break
            else:
                vals.append(def_val)

        def wrapper(coerce_func):
            def coerce_wrapper(obj, field, value):
                try:
                    val = coerce_func(obj, field, value)
                    if val is not None:
                        for check_func in vals:
                            check_func(val)
                    return val
                except (KeyError, ValueError, TypeError) as e:
                    msg = "Type: %s. Field: %s. Exception: %s" % (
                        obj.get_type_name(), field, str(e))
                    raise exc.BadRequest(message=msg)
            return coerce_wrapper

        field.coerce = wrapper(field.coerce)
        field.validators = vals
        return field

    @classmethod
    def init(cls, *args, **kwargs):
        """Fabric to build fields."""
        return cls(*args, **kwargs).get_field()


class CompoundField(Field):
    def __init__(self, field_class, element_type, element_validators=None,
                 **kwargs):
        if element_type is None:
            raise exc.IncorrectArtifactType("'element_type' must be set for "
                                            "compound type.")
        self.element_type = element_type

        super(CompoundField, self).__init__(field_class, **kwargs)

        self.vo_props.append('element_type')
        self.field_props.append('element_type')

        self.element_validators = element_validators or []
        if self.sortable:
            raise exc.IncorrectArtifactType("'sortable' must be False for "
                                            "compound type.")

    def get_element_validators(self):
        default_vals = []
        if issubclass(self.element_type, fields.String):
            # check if fields is string
            if not any(isinstance(v, val_lib.MaxStrLen)
                       for v in self.element_validators):
                default_vals.append(val_lib.MaxStrLen(255))
        vals = default_vals + self.element_validators
        for v in vals:
            v.check_type_allowed(self.element_type)
        return default_vals + self.element_validators


class ListField(CompoundField):
    def __init__(self, element_type, max_size=255, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = []
        if element_type is glare_fields.BlobField:
            raise exc.IncorrectArtifactType("List of blobs is not allowed "
                                            "to be specified in artifact.")
        super(ListField, self).__init__(glare_fields.List, element_type,
                                        **kwargs)
        self.validators.append(val_lib.MaxListSize(max_size))

    def get_default_validators(self):
        default_vals = []
        elem_val = val_lib.ListElementValidator(
            super(ListField, self).get_element_validators())
        default_vals.append(elem_val)
        return default_vals


class DictField(CompoundField):
    def __init__(self, element_type, max_size=255, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = {}
        super(DictField, self).__init__(glare_fields.Dict, element_type,
                                        **kwargs)
        self.validators.append(val_lib.MaxDictSize(max_size))

    def get_default_validators(self):
        default_vals = []
        elem_val = val_lib.DictElementValidator(
            super(DictField, self).get_element_validators())
        default_vals.append(elem_val)
        default_vals.append(val_lib.MaxDictKeyLen(255))
        default_vals.append(val_lib.MinDictKeyLen(1))
        return default_vals


class BlobField(Field):
    def __init__(self, max_blob_size=DEFAULT_MAX_BLOB_SIZE, **kwargs):
        super(BlobField, self).__init__(
            field_class=glare_fields.BlobField, **kwargs)
        self.max_blob_size = int(max_blob_size)
        self.field_props.append('max_blob_size')


class FolderField(DictField):
    def __init__(self, max_blob_size=DEFAULT_MAX_BLOB_SIZE,
                 max_folder_size=DEFAULT_MAX_FOLDER_SIZE, **kwargs):
        super(FolderField, self).__init__(
            element_type=glare_fields.BlobFieldType, **kwargs)
        self.max_blob_size = int(max_blob_size)
        self.max_folder_size = int(max_folder_size)
        self.field_props.append('max_blob_size')
        self.field_props.append('max_folder_size')

# Classes below added for backward compatibility. They shouldn't be used

Attribute = Field
CompoundAttribute = CompoundField
ListAttribute = ListField
DictAttribute = DictField
BlobAttribute = BlobField
BlobDictAttribute = FolderField
