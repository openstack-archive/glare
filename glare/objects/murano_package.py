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
from glare.objects.meta import validators
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Blob = wrappers.BlobField.init
List = wrappers.ListField.init
Dict = wrappers.DictField.init


class MuranoPackage(base.BaseArtifact):

    fields = {
        'package': Blob(required_on_activate=False,
                        description="Murano Package binary.",
                        max_blob_size=104857600),
        'type': Field(fields.StringField,
                      validators=[validators.AllowedValues(
                          ['Application', 'Library'])],
                      default='Application',
                      description="Package type."),
        'display_name': Field(fields.StringField, mutable=True,
                              description="Package name in human-readable "
                                          "format."),
        'categories': List(fields.String, mutable=True,
                           description="List of categories specified "
                                       "for the package."),
        'class_definitions': List(fields.String,
                                  validators=[validators.Unique()],
                                  description="List of class definitions in "
                                              "the package."),
        'inherits': Dict(fields.String),
        'keywords': List(fields.String, mutable=True),
        'dependencies': List(glare_fields.LinkFieldType,
                             required_on_activate=False,
                             description="List of package dependencies for "
                                         "this package."),
    }

    @classmethod
    def get_type_name(cls):
        return "murano_packages"

    @classmethod
    def get_display_type_name(cls):
        return "Murano packages"
