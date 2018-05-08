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

from glare.common import exception
from glare.objects import base
from glare.objects.meta import registry
from glare.objects.meta import wrappers


Field = wrappers.Field.init


class All(base.BaseArtifact):
    """Artifact type that allows to get artifacts regardless of their type"""

    fields = {
        'type_name': Field(fields.StringField,
                           description="Name of artifact type.",
                           sortable=True,
                           filter_ops=(wrappers.FILTER_LIKE,
                                       wrappers.FILTER_EQ,
                                       wrappers.FILTER_NEQ,
                                       wrappers.FILTER_IN))
    }

    @classmethod
    def create(cls, context):
        raise exception.Forbidden("This type is read only.")

    def save(self, context):
        raise exception.Forbidden("This type is read only.")

    @classmethod
    def delete(cls, context, af):
        raise exception.Forbidden("This type is read only.")

    @classmethod
    def update_blob(cls, context, af_id, field_name, values):
        raise exception.Forbidden("This type is read only.")

    @classmethod
    def get_type_name(cls):
        return "all"

    @classmethod
    def get_display_type_name(cls):
        return "All Artifacts"

    def to_dict(self):
        # Use specific method of artifact type to convert it to dict
        values = self.obj_to_primitive()['versioned_object.data']
        return registry.ArtifactRegistry.get_artifact_type(
            self.type_name).format_all(values)
