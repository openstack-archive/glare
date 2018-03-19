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

from oslo_versionedobjects import fields

from glare.objects import base
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Blob = wrappers.BlobField.init
Dict = wrappers.DictField.init
Folder = wrappers.FolderField.init


class HeatTemplate(base.BaseArtifact):

    fields = {
        'environments': Dict(glare_fields.LinkFieldType,
                             mutable=True,
                             description="References to Heat Environments "
                                         "that can be used with current "
                                         "template."),
        'template': Blob(description="Heat template body."),
        'nested_templates': Folder(description="Dict of nested templates "
                                               "where key is the name  of "
                                               "template and value is "
                                               "nested template body."),
        'default_envs': Dict(fields.String, mutable=True,
                             description="Default environments that can be "
                                         "applied to the template if no "
                                         "environments specified by user.")
    }

    @classmethod
    def get_type_name(cls):
        return "heat_templates"

    @classmethod
    def get_display_type_name(cls):
        return "Heat Templates"
