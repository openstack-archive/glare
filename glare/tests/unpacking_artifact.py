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

import io
import zipfile

from glare.common import exception
from glare.objects import base
from glare.objects.meta import file_utils
from glare.objects.meta import wrappers

Blob = wrappers.BlobField.init
Folder = wrappers.FolderField.init


class Unpacker(base.BaseArtifact):
    MAX_BLOB_SIZE = 100000

    fields = {
        'zip': Blob(description="Original zipped data.",
                    required_on_activate=False),
        'content': Folder(system=True, required_on_activate=False),
    }

    @classmethod
    def get_type_name(cls):
        return "unpacking_artifact"

    @classmethod
    def get_display_type_name(cls):
        return "Unpacking Artifact"

    @classmethod
    def pre_upload_hook(cls, context, af, field_name, blob_key, fd):
        flobj = io.BytesIO(fd.read(cls.MAX_BLOB_SIZE))

        # Raise exception if something left in the stream
        if fd.read(1):
            msg = ("The file you are trying to upload is too big. "
                   "The system upper limit is %s.") % cls.MAX_BLOB_SIZE
            raise exception.RequestEntityTooLarge(msg)

        zip_ref = zipfile.ZipFile(flobj, 'r')

        file_utils.unpack_zip_archive_to_artifact_folder(
            context, af, zip_ref, 'content')

        flobj.seek(0)
        return flobj
