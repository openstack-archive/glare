# Copyright 2017 Nokia
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

"""Contains additional file utils that may be useful for upload hooks."""

import os
import tempfile
import zipfile

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import uuidutils

from glare.common import store_api
from glare.common import utils
from glare.objects.meta import fields as glare_fields

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

INMEMORY_OBJECT_SIZE_LIMIT = 134217728  # 128 megabytes


def create_temporary_file(stream, suffix=''):
    """Create a temporary local file from a stream.

    :param stream: stream of bytes to be stored in a temporary file
    :param suffix: (optional) file name suffix
    """
    tfd, path = tempfile.mkstemp(suffix=suffix)
    while True:
        data = stream.read(100000)
        if data == b'':  # end of file reached
            break
        os.write(tfd, data)
    tfile = os.fdopen(tfd, "rb")
    return tfile, path


def extract_zip_to_temporary_folder(tfile):
    """Create temporary folder and extract all file contents there.

    :param tfile: zip archive to be extracted
    """
    zip_ref = zipfile.ZipFile(tfile, 'r')
    tdir = tempfile.mkdtemp()
    zip_ref.extractall(tdir)
    zip_ref.close()
    return tdir


def unpack_zip_archive_to_artifact_folder(context, af, zip_ref, folder_name):
    """Unpack zip archive to artifact folder.

    :param context: user context
    :param af: artifact object
    :param zip_ref: zip archive to be extracted
    :param folder_name: name of the artifact folder where to extract data
    """
    file_dict = {}
    blobs = []
    for name in zip_ref.namelist():
        if not name.endswith('/'):
            blob_id = uuidutils.generate_uuid()
            # create an an empty blob instance in db with 'saving' status
            blob = {'url': None, 'size': None, 'md5': None, 'sha1': None,
                    'sha256': None, 'status': 'saving', 'id': blob_id,
                    'external': False,
                    'content_type': 'application/octet-stream'}
            file_dict[name] = blob
            blobs.append((blob_id, utils.BlobIterator(zip_ref.read(name))))

    setattr(af, folder_name, file_dict)
    af = af.update_blob(context, af.id, folder_name, file_dict)

    default_store = getattr(
        CONF, 'artifact_type:' + af.get_type_name()).default_store
    # use global parameter if default store isn't set per artifact type
    if default_store is None:
        default_store = CONF.glance_store.default_store

    # try to perform blob uploading to storage backend
    try:
        blobs_info = store_api.save_blobs_to_store(
            blobs, context, af.get_max_blob_size(folder_name),
            default_store)
        for name in zip_ref.namelist():
            if not name.endswith('/'):
                location_uri, size, checksums = blobs_info[
                    file_dict[name]['id']]
                # update blob info and activate it
                file_dict[name].update({'url': location_uri,
                                        'status': 'active',
                                        'size': size})
                file_dict[name].update(checksums)
    except Exception:
        # if upload failed remove blob from db and storage
        with excutils.save_and_reraise_exception(logger=LOG):
            af.update_blob(context, af.id, folder_name, None)

    af.update_blob(context, af.id, folder_name, file_dict)


def upload_content_file(context, af, data, blob_dict, key_name,
                        content_type='application/octet-stream'):
    """Upload a file to a blob dictionary.

    :param context: user context
    :param af: artifact object
    :param data: bytes that need to be stored in the blob dictionary
    :param blob_dict: name of the blob_dictionary field
    :param key_name: name of key in the dictionary
    :param content_type: (optional) specifies mime type of uploading data
    """
    blob_id = uuidutils.generate_uuid()
    # create an an empty blob instance in db with 'saving' status
    blob = {'url': None, 'size': None, 'md5': None, 'sha1': None,
            'sha256': None, 'status': glare_fields.BlobFieldType.SAVING,
            'external': False, 'content_type': content_type, 'id': blob_id}

    getattr(af, blob_dict)[key_name] = blob
    af = af.update_blob(context, af.id, blob_dict, getattr(af, blob_dict))

    # try to perform blob uploading to storage backend
    try:
        default_store = getattr(
            CONF, 'artifact_type:' + af.get_type_name()).default_store
        # use global parameter if default store isn't set per artifact type
        if default_store is None:
            default_store = CONF.glance_store.default_store

        location_uri, size, checksums = store_api.save_blob_to_store(
            blob_id, data, context, af.get_max_blob_size(blob_dict),
            default_store)
    except Exception:
        # if upload failed remove blob from db and storage
        with excutils.save_and_reraise_exception(logger=LOG):
            del getattr(af, blob_dict)[key_name]
            af = af.update_blob(context, af.id,
                                blob_dict, getattr(af, blob_dict))
    # update blob info and activate it
    blob.update({'url': location_uri,
                 'status': glare_fields.BlobFieldType.ACTIVE,
                 'size': size})
    blob.update(checksums)
    getattr(af, blob_dict)[key_name] = blob
    af.update_blob(context, af.id, blob_dict, getattr(af, blob_dict))
