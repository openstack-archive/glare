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

"""Sample artifact object for testing purposes"""
import io

from glare.common.utils import CooperativeReader
from oslo_versionedobjects import fields

from glare.common.exception import GlareException
from glare.objects import base as base_artifact
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Dict = wrappers.DictField.init
List = wrappers.ListField.init
Blob = wrappers.BlobField.init
Folder = wrappers.FolderField.init


class SampleArtifact(base_artifact.BaseArtifact):
    VERSION = '1.0'

    fields = {
        'blob': Blob(required_on_activate=False, mutable=True,
                     description="I am Blob"),
        'small_blob': Blob(max_blob_size=10, required_on_activate=False,
                           mutable=True),
        'link1': Field(glare_fields.Link,
                       required_on_activate=False),
        'link2': Field(glare_fields.Link,
                       required_on_activate=False),
        'bool1': Field(fields.FlexibleBooleanField,
                       required_on_activate=False,
                       filter_ops=(wrappers.FILTER_EQ,),
                       default=False),
        'bool2': Field(fields.FlexibleBooleanField,
                       required_on_activate=False,
                       filter_ops=(wrappers.FILTER_EQ,),
                       default=False),
        'int1': Field(fields.IntegerField,
                      required_on_activate=False,
                      sortable=True),
        'int2': Field(fields.IntegerField,
                      sortable=True,
                      required_on_activate=False),
        'float1': Field(fields.FloatField,
                        sortable=True,
                        required_on_activate=False),
        'float2': Field(fields.FloatField,
                        sortable=True,
                        required_on_activate=False),
        'str1': Field(fields.StringField,
                      filter_ops=(wrappers.FILTER_LIKE,
                                  wrappers.FILTER_EQ,
                                  wrappers.FILTER_NEQ,
                                  wrappers.FILTER_IN),
                      sortable=True,
                      required_on_activate=False),
        'list_of_str': List(fields.String,
                            required_on_activate=False,
                            filter_ops=(wrappers.FILTER_EQ,
                                        wrappers.FILTER_IN)),
        'list_of_int': List(fields.Integer,
                            required_on_activate=False,
                            filter_ops=(wrappers.FILTER_EQ,
                                        wrappers.FILTER_IN)),
        'dict_of_str': Dict(fields.String,
                            required_on_activate=False,
                            filter_ops=(wrappers.FILTER_EQ,
                                        wrappers.FILTER_IN)),
        'dict_of_int': Dict(fields.Integer,
                            required_on_activate=False,
                            filter_ops=(wrappers.FILTER_EQ,
                                        wrappers.FILTER_IN)),
        'dict_of_links': Dict(glare_fields.LinkFieldType,
                              mutable=True,
                              required_on_activate=False,
                              filter_ops=(wrappers.FILTER_EQ,)),
        'list_of_links': List(glare_fields.LinkFieldType,
                              mutable=True,
                              required_on_activate=False,
                              filter_ops=(wrappers.FILTER_EQ,)),
        'dict_of_blobs': Folder(required_on_activate=False,
                                max_folder_size=2000,
                                validators=[
                                    validators.MaxDictKeyLen(1000)]),
        'string_mutable': Field(fields.StringField,
                                required_on_activate=False,
                                mutable=True),
        'string_regex': Field(fields.StringField,
                              required_on_activate=False,
                              validators=[
                                  validators.Regex('^([0-9a-fA-F]){8}$')]),
        'string_required': Field(fields.StringField,
                                 required_on_activate=True),
        'string_validators': Field(fields.StringField,
                                   required_on_activate=False,
                                   validators=[
                                       validators.AllowedValues(
                                           ['aa', 'bb', 'c' * 11]),
                                       validators.MaxStrLen(10)
                                   ]),
        'int_validators': Field(fields.IntegerField,
                                required_on_activate=False,
                                validators=[
                                    validators.MinNumberSize(10),
                                    validators.MaxNumberSize(20)
                                ]),
        'list_validators': List(fields.String,
                                required_on_activate=False,
                                filter_ops=[],
                                max_size=3,
                                validators=[validators.Unique()]),
        'dict_validators': Dict(fields.String,
                                required_on_activate=False,
                                default=None,
                                filter_ops=[],
                                validators=[
                                    validators.AllowedDictKeys([
                                        'abc', 'def', 'ghi', 'jkl'])],
                                max_size=3),
        'system_attribute': Field(fields.StringField,
                                  system=True, sortable=True,
                                  default="default"),
        'metadata_attribute': Field(fields.StringField, default="default",
                                    metadata={"metadata1": "value1",
                                              "metadata2": "blahblahblah"})
    }

    @classmethod
    def get_type_name(cls):
        return "sample_artifact"

    @classmethod
    def get_display_type_name(cls):
        return "Sample Artifact"

    @classmethod
    def pre_upload_hook(cls, context, af, field_name, blob_key, fd):
        flobj = io.BytesIO(CooperativeReader(fd).read())
        data = flobj.read()
        print("Data in pre_upload_hook: %s" % data)
        if data == b'invalid_data':
            raise GlareException("Invalid Data found")
        # Try to seek same fd to 0.
        try:
            fd.seek(0)
        except Exception:  # catch Exception in case fd is non-seekable.
            flobj.seek(0)
            return flobj
        return fd

    def to_dict(self):
        res = self.obj_to_primitive()['versioned_object.data']
        res['__some_meta_information__'] = res['name'].upper()
        return res

    @classmethod
    def format_all(cls, values):
        values['__some_meta_information__'] = values['name'].upper()
        return values
