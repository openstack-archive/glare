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

from oslo_versionedobjects import fields

from glare.objects import base as base_artifact
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Dict = wrappers.DictField.init
List = wrappers.ListField.init
Blob = wrappers.BlobField.init
Folder = wrappers.FolderField.init


class NonNullableFieldsArtifact(base_artifact.BaseArtifact):
    """For testing purposes: check the case of creating artifact that
     has nullable=false field without any default
     """

    fields = {
        'int_not_nullable_with_default': Field(fields.IntegerField,
                                               nullable=False, default=0,
                                               required_on_activate=False),
        'int_not_nullable_without_default': Field(fields.IntegerField,
                                                  nullable=False)
    }

    @classmethod
    def get_type_name(cls):
        return "non_nullable_fields_artifact"

    @classmethod
    def get_display_type_name(cls):
        return "not Nullable Fields Artifact"

    def to_dict(self):
        res = self.obj_to_primitive()['versioned_object.data']
        res['__some_meta_information__'] = res['name'].upper()
        return res

    @classmethod
    def format_all(cls, values):
        values['__some_meta_information__'] = values['name'].upper()
        return values
