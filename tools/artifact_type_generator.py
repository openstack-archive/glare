# Copyright 2017 - Nokia Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import argparse
import datetime

# Usage:
# python artifact_type_generator.py my_artifacts \
# --version 1.1 \
# --fields my_str:String,my_int:Integer,my_dict_of_ints:IntegerDict,\
# my_list_of_links:LinkList \
# --output my_artifacts.py

sample = """# Copyright {year} OpenStack Foundation
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

# Import fields from oslo.vo
from oslo_versionedobjects import fields

# Import glare addons:
# The parent class for all artifacts inherited from
# oslo_versionedobjects.base.VersionedObject
from glare.objects import base as base_artifact

# Glare wrapper for oslo_versionedobjects.fields
from glare.objects.meta import wrappers

# Additional Glare field types
from glare.objects.meta import fields as glare_fields

# Collection of objects that can be attached to a field and set some
# limitations on them
from glare.objects.meta import validators

# Basic field wrapper. May contain String, Integer, Float, Boolean or Link
Field = wrappers.Field.init
# Dictionary wrapper for primitive types
Dict = wrappers.DictField.init
# List wrapper for primitive types
List = wrappers.ListField.init
# Wrapper for a file
Blob = wrappers.BlobField.init
# Wrapper for a folder of files
Folder = wrappers.FolderField.init


class {class_name}(base_artifact.BaseArtifact):
    # Initially it's recommended to set artifact type version as 1.0
    VERSION = '{type_version}'

    # Obligatory method that returns artifact type name
    @classmethod
    def get_type_name(cls):
        return '{type_name}'

    # All fields are specified in 'fields' dictionary (oslo_vo requirement)
    # Each artifact field has several common properties:
    # * required_on_activate - boolean value indicating if the field value
    #   should be specified for the artifact before activation. (Default: True)
    #
    # * mutable - boolean value indicating if the field value may be changed
    #   after the artifact is activated. (Default: False)
    #
    # * system - boolean value indicating if the field value cannot be edited
    #   by user. (Default: False)
    #
    # * sortable - boolean value indicating if there is a possibility to sort
    #   by this fields's values. (Default: False)
    #   Only fields of 4 primitive types can be sortable:
    #   integer, string, float and boolean.
    #
    # * default - a default value for the field may be specified
    #   (Default: None)
    #
    # * validators - a list of objects. When user sets a value to the field
    #   with additional validators Glare checks them before setting the value
    #   and raises ValueError if at least one of the requirements is not
    #   satisfied.
    #   The full collection of implemented validators you can find at
    #   glare/objects/meta/validators
    #
    # * filter_ops - a list of available filter operators for the field.
    #   There are seven available operators:
    #   'eq', 'neq', 'lt', 'lte', 'gt', 'gte', 'in'.

    fields = {{
    {fields}
    }}

    # Here it goes a collection of possible operational hooks:
    @classmethod
    def pre_create_hook(cls, context, af):
        pass

    @classmethod
    def post_create_hook(cls, context, af):
        pass

    @classmethod
    def pre_update_hook(cls, context, af):
        pass

    @classmethod
    def post_update_hook(cls, context, af):
        pass

    @classmethod
    def pre_activate_hook(cls, context, af):
        pass

    @classmethod
    def post_activate_hook(cls, context, af):
        pass

    @classmethod
    def pre_publish_hook(cls, context, af):
        pass

    @classmethod
    def post_publish_hook(cls, context, af):
        pass

    @classmethod
    def pre_deactivate_hook(cls, context, af):
        pass

    @classmethod
    def post_deactivate_hook(cls, context, af):
        pass

    @classmethod
    def pre_reactivate_hook(cls, context, af):
        pass

    @classmethod
    def post_reactivate_hook(cls, context, af):
        pass

    @classmethod
    def pre_upload_hook(cls, context, af, field_name, blob_key, fd):
        return fd

    @classmethod
    def post_upload_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def pre_add_location_hook(
            cls, context, af, field_name, blob_key, location):
        pass

    @classmethod
    def post_add_location_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def pre_download_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def post_download_hook(cls, context, af, field_name, blob_key, fd):
        return fd

    @classmethod
    def pre_delete_hook(cls, context, af):
        pass

    @classmethod
    def post_delete_hook(cls, context, af):
        pass
"""


string_field_sample = """
        "{field_name}": Field(
            fields.StringField,
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            filter_ops=('eq', 'neq', 'in'),
            validators=[]),"""

integer_field_sample = """
        "{field_name}": Field(
            fields.IntegerField,
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            filter_ops=('eq', 'neq', 'in', 'gt', 'gte', 'lt', 'lte'),
            validators=[]),"""

float_field_sample = """
        "{field_name}": Field(
            fields.FloatField,
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            filter_ops=('eq', 'neq', 'in', 'gt', 'gte', 'lt', 'lte'),
            validators=[]),"""

boolean_field_sample = """
        "{field_name}": Field(
            fields.FlexibleBooleanFieldField,
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            filter_ops=('eq', 'neq'),
            validators=[]),"""

link_field_sample = """
        "{field_name}": Field(
            glare_fields.Link,
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            filter_ops=('eq', 'neq'),
            validators=[]),"""

blob_field_sample = """
        "{field_name}": Blob(
            max_blob_size=10485760,  # 10 Megabytes
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            validators=[]),"""

folder_field_sample = """
        "{field_name}": Folder(
            max_blob_size=10485760,  # 10 Megabytes
            max_folder_size = 2673868800,  # 2550 Megabytes
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            validators=[]),"""

dict_field_sample = """
        "{field_name}": Dict(
            {element_type},
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            validators=[],
            element_validators=[]),"""

list_field_sample = """
        "{field_name}": List(
            {element_type},
            default=None,
            required_on_activate=True,
            mutable=False,
            system=False,
            validators=[],
            element_validators=[]),"""


def get_parser():
    parser = argparse.ArgumentParser(
        description='Generates a sample file for an artifact type.',
        usage="python artifact_type_generator.py <type_name> -o <output_file>"
    )
    parser.add_argument(
        'name',
        metavar='<ARTIFACT_TYPE_NAME>',
        help='Name of the artifact type you want to create.'
    )
    parser.add_argument(
        '--version', '-v',
        metavar='<ARTIFACT_TYPE_version>',
        help='Version of the artifact type you want to create.',
        default='1.0'
    )
    parser.add_argument(
        '--output', '-o',
        metavar='<OUTPUT_FILE>',
        help='Name of the generated file.',
    )
    parser.add_argument(
        '--fields', '-f',
        metavar='<TYPE_FIELDS>',
        help='List of fields artifact type should contain.',
        default=''
    )
    return parser


def generate_fields(fields):
    output = []
    for field_name, field_type in fields.items():
        field_type = field_type.lower()
        if field_type == 'string':
            output.append(string_field_sample.format(field_name=field_name))
        elif field_type == 'integer':
            output.append(integer_field_sample.format(field_name=field_name))
        elif field_type == 'float':
            output.append(float_field_sample.format(field_name=field_name))
        elif field_type == 'boolean':
            output.append(boolean_field_sample.format(field_name=field_name))
        elif field_type == 'link':
            output.append(link_field_sample.format(field_name=field_name))
        elif field_type == 'blob':
            output.append(blob_field_sample.format(field_name=field_name))
        elif field_type == 'folder':
            output.append(folder_field_sample.format(field_name=field_name))
        elif field_type.endswith('dict'):
            element_type = field_type[:-4].capitalize()
            if element_type == 'Boolean':
                element_type = 'fields.FlexibleBoolean'
            elif element_type == 'Link':
                element_type = 'glare_fields.LinkFieldType'
            else:
                element_type = 'fields.' + element_type
            output.append(dict_field_sample.format(
                field_name=field_name, element_type=element_type))
        elif field_type.endswith('list'):
            element_type = field_type[:-4].capitalize()
            if element_type == 'Boolean':
                element_type = 'fields.FlexibleBoolean'
            elif element_type == 'Link':
                element_type = 'glare_fields.LinkFieldType'
            else:
                element_type = 'fields.' + element_type
            output.append(list_field_sample.format(
                field_name=field_name, element_type=element_type))

    return ''.join(output)


if __name__ == "__main__":

    args = get_parser().parse_args()

    fields = dict(field.split(':') for field in args.fields.split(','))

    values = {
        'type_name': args.name,
        # Change my_cool_artifacts to MyCoolArtifacts
        'class_name': ''.join(map(str.capitalize, args.name.split('_'))),
        'type_version': args.version,
        'fields': generate_fields(fields),
        'year': str(datetime.datetime.now().year)
    }

    if args.output is not None:
        with open(args.output, 'w') as f:
            f.write(sample.format(**values))
    else:
        print(sample.format(**values))
