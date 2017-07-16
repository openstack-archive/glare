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

import os
import shutil

from oslo_config import cfg
from oslo_log import log as logging
from oslo_versionedobjects import fields

from glare.common import exception
from glare.objects import base
from glare.objects.meta import file_utils
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
        'zip': Blob(description="Original zipped data.",
                    required_on_activate=False),
        'content': Folder(system=True, required_on_activate=False),
        'forbid_activate': Field(fields.FlexibleBooleanField,
                                 default=False),
        'forbid_publish': Field(fields.FlexibleBooleanField,
                                default=False, mutable=True),
        'forbid_download_zip': Field(fields.FlexibleBooleanField,
                                     default=False),
        'forbid_delete': Field(fields.FlexibleBooleanField,
                               default=False, mutable=True),
    }

    artifact_type_opts = base.BaseArtifact.artifact_type_opts + [
        cfg.BoolOpt('in_memory_processing')
    ]

    @classmethod
    def get_type_name(cls):
        return "hooks_artifact"

    @classmethod
    def _validate_upload_harddrive(cls, context, af, field_name, fd):
        path = None
        tdir = None
        try:
            tfile, path = file_utils.create_temporary_file(fd, '.zip')
            tdir = file_utils.extract_zip_to_temporary_folder(tfile)

            # upload all files to 'content' folder
            for subdir, dirs, files in os.walk(tdir):
                for file_name in files:
                    path_to_file = os.path.join(subdir, file_name)
                    with open(path_to_file, "rb") as f:
                        file_utils.upload_content_file(
                            context, af, f, 'content',
                            path_to_file[len(tdir) + 1:])
        except Exception as e:
            if path is not None and os.path.exists(path):
                # remove temporary file if something went wrong
                os.remove(path)
            raise e
        finally:
            # remove temporary folder
            if tdir is not None:
                shutil.rmtree(tdir)

        tfile.flush()
        tfile.seek(0)
        return tfile, path

    @classmethod
    def validate_upload(cls, context, af, field_name, fd):
        if getattr(CONF, 'artifact_type:hooks_artifact').in_memory_processing:
            return file_utils.unpack_zip_archive_in_memory(
                context, af, 'content', fd), None
        else:
            return cls._validate_upload_harddrive(
                context, af, field_name, fd)

    @classmethod
    def validate_download(cls, context, af, field_name, fd):
        if af.forbid_download_zip and field_name == 'zip':
            raise exception.BadRequest
        return fd, None

    @classmethod
    def validate_activate(cls, context, af):
        if af.forbid_activate:
            raise exception.BadRequest

    @classmethod
    def validate_publish(cls, context, af):
        if af.forbid_publish:
            raise exception.BadRequest

    @classmethod
    def validate_delete(cls, context, af):
        if af.forbid_delete:
            raise exception.BadRequest
