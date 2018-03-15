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

import tempfile

from oslo_config import cfg
from oslo_log import log as logging
from oslo_versionedobjects import fields

from glare.objects import base
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Dict = wrappers.DictField.init
List = wrappers.ListField.init
Blob = wrappers.BlobField.init
Folder = wrappers.FolderField.init

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class HookChecker(base.BaseArtifact):
    fields = {
        'temp_dir': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_create': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_update': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_activate': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_reactivate': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_deactivate': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'temp_file_path_publish': Field(
            fields.StringField,
            required_on_activate=False,
            mutable=True),
        'blob': Blob(
            required_on_activate=False,
            mutable=True)
    }

    artifact_type_opts = [
        cfg.StrOpt('temp_file_path')
    ]

    @classmethod
    def get_type_name(cls):
        return "hooks_artifact"

    @classmethod
    def get_display_type_name(cls):
        return "Hooks Artifact"

    @classmethod
    def pre_create_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_create = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_create, 'w') as f:
            f.write('pre_create_hook was called\n')

    @classmethod
    def post_create_hook(cls, context, af):
        with open(af.temp_file_path_create, 'a') as f:
            f.write('post_create_hook was called\n')

    @classmethod
    def pre_update_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_update = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_update, 'w') as f:
            f.write('pre_update_hook was called\n')

    @classmethod
    def post_update_hook(cls, context, af):
        with open(af.temp_file_path_update, 'a') as f:
            f.write('post_update_hook was called\n')

    @classmethod
    def pre_activate_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_activate = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_activate, 'w') as f:
            f.write('pre_activate_hook was called\n')

    @classmethod
    def post_activate_hook(cls, context, af):
        with open(af.temp_file_path_activate, 'a') as f:
            f.write('post_activate_hook was called\n')

    @classmethod
    def pre_publish_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_publish = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_publish, 'w') as f:
            f.write('pre_publish_hook was called\n')

    @classmethod
    def post_publish_hook(cls, context, af):
        with open(af.temp_file_path_publish, 'a') as f:
            f.write('post_publish_hook was called\n')

    @classmethod
    def pre_deactivate_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_deactivate = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_deactivate, 'w') as f:
            f.write('pre_deactivate_hook was called\n')

    @classmethod
    def post_deactivate_hook(cls, context, af):
        with open(af.temp_file_path_deactivate, 'a') as f:
            f.write('post_deactivate_hook was called\n')

    @classmethod
    def pre_reactivate_hook(cls, context, af):
        # create a temporary file and set the path to artifact field
        __, af.temp_file_path_reactivate = tempfile.mkstemp(dir=af.temp_dir)
        with open(af.temp_file_path_reactivate, 'w') as f:
            f.write('pre_reactivate_hook was called\n')

    @classmethod
    def post_reactivate_hook(cls, context, af):
        with open(af.temp_file_path_reactivate, 'a') as f:
            f.write('post_reactivate_hook was called\n')

    @classmethod
    def pre_upload_hook(cls, context, af, field_name, blob_key, fd):
        # create a temporary file and set the path to artifact field
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'w') as f:
                f.write('pre_upload_hook was called\n')
        return fd

    @classmethod
    def post_upload_hook(cls, context, af, field_name, blob_key):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'a') as f:
                f.write('post_upload_hook was called\n')

    @classmethod
    def pre_add_location_hook(
            cls, context, af, field_name, blob_key, location):
        # create a temporary file and set the path to artifact field
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'w') as f:
                f.write('pre_add_location_hook was called\n')

    @classmethod
    def post_add_location_hook(cls, context, af, field_name, blob_key):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'a') as f:
                f.write('post_add_location_hook was called\n')

    @classmethod
    def pre_download_hook(cls, context, af, field_name, blob_key):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'a') as f:
                f.write('pre_download_hook was called\n')

    @classmethod
    def post_download_hook(cls, context, af, field_name, blob_key, fd):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'a') as f:
                f.write('post_download_hook was called\n')
        return fd

    @classmethod
    def pre_delete_hook(cls, context, af):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'w') as f:
                f.write('pre_delete_hook was called\n')

    @classmethod
    def post_delete_hook(cls, context, af):
        file_path = getattr(
            CONF, 'artifact_type:hooks_artifact').temp_file_path
        if file_path:
            with open(file_path, 'a') as f:
                f.write('post_delete_hook was called\n')
