# Copyright 2017 OpenStack Foundation
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

from glare.objects import base as base_artifact
from glare.objects.meta import validators
from glare.objects.meta import wrappers
from oslo_versionedobjects import fields

Field = wrappers.Field.init
Blob = wrappers.BlobField.init
Dict = wrappers.DictField.init
Folder = wrappers.FolderField.init


class Secret(base_artifact.BaseArtifact):
    """The purpose this glare artifact, Secret, is to enable the user to store
    'secret' data such as: Private key, Certificate, Password, SSH keys Etc.
    """
    VERSION = '1.0'

    @classmethod
    def get_type_name(cls):
        return "secrets"

    @classmethod
    def get_display_type_name(cls):
        return "Secrets"

    fields = {
        'payload': Blob(  # The encrypted secret data
            description="The secret's data to be stored"
        ),

        'payload_content_encoding': Field(
            fields.StringField,
            required_on_activate=False,
            default="base64",
            filter_ops=[],
            validators=[validators.AllowedValues(["base64"])],
            description="Required if payload is encoded. "
                        "The encoding used for the payload to be"
                        " able to include it in the JSON request "
                        "(only base64 supported)"
        ),

        'secret_type': Field(
            fields.StringField,
            required_on_activate=False,
            default="opaque",
            sortable=True,
            filter_ops=(wrappers.FILTER_EQ,),
            validators=[validators.AllowedValues([
                "symmetric", "public", "private",
                "passphrase", "certificate", "opaque"])],
            description="Used to indicate the type of secret being stored",
        ),

        'algorithm': Field(
            fields.StringField,
            required_on_activate=False,
            filter_ops=(wrappers.FILTER_EQ,),
            description="Metadata provided by a user or system for"
                        " informational purposes"
        ),

        'bit_length': Field(
            fields.IntegerField,
            required_on_activate=False,
            sortable=True,
            validators=[validators.MinNumberSize(1)],
            description="Metadata provided by a user or system"
                        " for informational purposes."
                        " Value must be greater than zero."
        ),

        'mode': Field(
            fields.StringField,
            required_on_activate=False,
            filter_ops=(wrappers.FILTER_EQ,),
            description="Metadata provided by a user or"
                        " system for informational purposes."),
    }
