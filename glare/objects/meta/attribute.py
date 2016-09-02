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

import six

from oslo_versionedobjects import fields

from glare.common import exception as exc
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators as val_lib

FILTERS = (
    FILTER_EQ, FILTER_NEQ, FILTER_IN, FILTER_GT, FILTER_GTE, FILTER_LT,
    FILTER_LTE) = ('eq', 'neq', 'in', 'gt', 'gte', 'lt', 'lte')


class Attribute(object):
    def __init__(self, field_class, mutable=False, required_on_activate=True,
                 system=False, validators=None, nullable=True, default=None,
                 sortable=False, filter_ops=None, description=""):
        """Init and validate attribute"""
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
                        "It's forbidden to make attribute %(attr)s "
                        "sortable if string length can be more than 255 "
                        "symbols. Maximal allowed length now: %(max)d" %
                        {"attr": str(field_class), 'max': v.size})

        self.field_class = field_class
        self.nullable = nullable
        self.default = default
        self.vo_attrs = ['nullable', 'default']

        self.mutable = mutable
        self.required_on_activate = required_on_activate
        self.system = system
        self.sortable = sortable
        if field_class is not glare_fields.BlobField:
            self.filter_ops = filter_ops or [FILTER_EQ, FILTER_NEQ, FILTER_IN]
        else:
            if filter_ops:
                raise exc.IncorrectArtifactType(
                    "Cannot specify filters for blobs")
            self.filter_ops = []
        self.field_attrs = ['mutable', 'required_on_activate', 'system',
                            'sortable', 'filter_ops', 'description']
        self.description = description

    def get_default_validators(self):
        default = []
        if issubclass(self.field_class, fields.StringField):
            # check if fields is string
            if not any(isinstance(v, val_lib.MaxStrLen)
                       for v in self.validators):
                default.append(val_lib.MaxStrLen(255))
        return default

    def get_field(self):
        # init the field
        vo_attrs = {attr_name: getattr(self, attr_name)
                    for attr_name in self.vo_attrs}
        field = self.field_class(**vo_attrs)
        # setup custom field attrs
        field_attrs = {attr_name: getattr(self, attr_name)
                       for attr_name in self.field_attrs}
        for prop, value in six.iteritems(field_attrs):
                setattr(field, prop, value)

        # apply custom validators
        vals = self.validators + self.get_default_validators()

        def wrapper(coerce_func):
            def coerce_wrapper(obj, attr, value):
                try:
                    val = coerce_func(obj, attr, value)
                    if val is not None:
                        for check_func in vals:
                            check_func(val)
                    return val
                except (KeyError, ValueError, TypeError) as e:
                    msg = "Type: %s. Field: %s. Exception: %s" % (
                        obj.get_type_name(), attr, str(e))
                    raise exc.BadRequest(message=msg)
            return coerce_wrapper

        field.coerce = wrapper(field.coerce)
        field.validators = vals
        return field

    @classmethod
    def init(cls, *args, **kwargs):
        """Fabric to build attributes"""
        return cls(*args, **kwargs).get_field()


class CompoundAttribute(Attribute):
    def __init__(self, field_class, element_type, element_validators=None,
                 **kwargs):
        super(CompoundAttribute, self).__init__(field_class, **kwargs)
        if self.sortable:
            raise exc.IncorrectArtifactType("'sortable' must be False for "
                                            "compound type.")

        if element_type is None:
            raise exc.IncorrectArtifactType("'element_type' must be set for "
                                            "compound type.")
        self.element_type = element_type
        self.vo_attrs.append('element_type')
        self.field_attrs.append('element_type')

        self.element_validators = element_validators or []

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


class ListAttribute(CompoundAttribute):
    def __init__(self, element_type, max_size=255, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = []
        if element_type is glare_fields.BlobField:
            raise exc.IncorrectArtifactType("List of blobs is not allowed "
                                            "to be specified in artifact.")
        super(ListAttribute, self).__init__(glare_fields.List, element_type,
                                            **kwargs)
        self.validators.append(val_lib.MaxListSize(max_size))

    def get_default_validators(self):
        default_vals = []
        elem_val = val_lib.ListElementValidator(
            super(ListAttribute, self).get_element_validators())
        default_vals.append(elem_val)
        return default_vals


class DictAttribute(CompoundAttribute):
    def __init__(self, element_type, max_size=255, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = {}
        super(DictAttribute, self).__init__(glare_fields.Dict, element_type,
                                            **kwargs)
        self.validators.append(val_lib.MaxDictSize(max_size))
        if element_type is glare_fields.BlobFieldType:
            self.filter_ops = []

    def get_default_validators(self):
        default_vals = []
        elem_val = val_lib.DictElementValidator(
            super(DictAttribute, self).get_element_validators())
        default_vals.append(elem_val)
        default_vals.append(val_lib.MaxDictKeyLen(255))
        return default_vals


class BlobAttribute(Attribute):
    DEFAULT_MAX_BLOB_SIZE = 10485760

    def __init__(self, max_blob_size=DEFAULT_MAX_BLOB_SIZE, **kwargs):
        super(BlobAttribute, self).__init__(
            field_class=glare_fields.BlobField, **kwargs)
        self.max_blob_size = int(max_blob_size)
        self.field_attrs.append('max_blob_size')


class BlobDictAttribute(DictAttribute):
    def __init__(self, max_blob_size=BlobAttribute.DEFAULT_MAX_BLOB_SIZE,
                 **kwargs):
        super(BlobDictAttribute, self).__init__(
            element_type=glare_fields.BlobFieldType, **kwargs)
        self.max_blob_size = int(max_blob_size)
        self.field_attrs.append('max_blob_size')
