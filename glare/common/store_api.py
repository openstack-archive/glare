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

from glance_store import backend
from glance_store import exceptions as store_exc
from oslo_config import cfg
from oslo_log import log as logging

from glare.common import exception
from glare.common import utils
from glare.store import database

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
database_api = database.DatabaseStoreAPI()
# we restrict several schemes because of potential security bugs.
# read more about the bugs here:
# https://bugs.launchpad.net/glance/+bug/942118
# https://bugs.launchpad.net/glance/+bug/1400966
# https://bugs.launchpad.net/glance/+bug/1334196
RESTRICTED_URI_SCHEMES = ('file', 'filesystem', 'swift+config', 'sql')

error_map = [{'catch': store_exc.NotFound,
              'raise': exception.NotFound},
             {'catch': store_exc.UnknownScheme,
              'raise': exception.BadRequest},
             {'catch': store_exc.BadStoreUri,
              'raise': exception.BadRequest},
             {'catch': store_exc.Duplicate,
              'raise': exception.Conflict},
             {'catch': store_exc.StorageFull,
              'raise': exception.Forbidden},
             {'catch': store_exc.StorageWriteDenied,
              'raise': exception.Forbidden},
             {'catch': store_exc.Forbidden,
              'raise': exception.Forbidden},
             {'catch': store_exc.Invalid,
              'raise': exception.BadRequest},
             {'catch': store_exc.BadStoreConfiguration,
              'raise': exception.GlareException},
             {'catch': store_exc.RemoteServiceUnavailable,
              'raise': exception.BadRequest},
             {'catch': store_exc.HasSnapshot,
              'raise': exception.Conflict},
             {'catch': store_exc.InUseByStore,
              'raise': exception.Conflict},
             {'catch': store_exc.BackendException,
              'raise': exception.GlareException},
             {'catch': store_exc.GlanceStoreException,
              'raise': exception.GlareException}]


@utils.error_handler(error_map)
def save_blob_to_store(blob_id, blob, context, max_size,
                       store_type=None, verifier=None):
    """Save file to specified store type and return location info to the user.

    :param store_type: type of the store, None means save to default store.
    :param blob_id: id of blob
    :param blob: blob file iterator
    :param context: user context
    :param verifier:signature verified
    :return: tuple of values: (location_uri, size, checksums)
    """
    data = utils.LimitingReader(utils.CooperativeReader(blob), max_size)

    LOG.debug('Start uploading blob %s.', blob_id)
    if store_type == 'database':
        location = database_api.add_to_backend(
            blob_id, data, context, verifier)
    else:
        (location, size, md5checksum, __) = backend.add_to_backend(
            CONF, blob_id, data, 0, store_type, context, verifier)
    LOG.debug('Uploading of blob %s is finished.', blob_id)

    checksums = {"md5": data.md5.hexdigest(),
                 "sha1": data.sha1.hexdigest(),
                 "sha256": data.sha256.hexdigest()}
    return location, data.bytes_read, checksums


@utils.error_handler(error_map)
def save_blobs_to_store(blobs, context, max_size,
                        store_type=None, verifier=None):
    """Save several files to specified store.

    :param store_type: type of the store, None means save to default store.
    :param blobs: list of tuples (blob_data_id, data)
    :param context: user context
    :param verifier:signature verified
    :return: dict {blob_data_id: (location_uri, size, checksums)}
    """
    # wrap data in CooperativeReader
    blobs = [(blob_data_id,
              utils.LimitingReader(utils.CooperativeReader(data), max_size))
             for (blob_data_id, data) in blobs]

    if store_type == 'database':
        locations = database_api.add_to_backend_batch(blobs, context, verifier)
    else:
        locations = []
        for blob_data_id, data in blobs:
            (location, __, __, __) = backend.add_to_backend(
                CONF, blob_data_id, data, 0, store_type, context, verifier)
            locations.append(location)

    # combine location, size and checksums together
    res = {}
    for i in range(len(locations)):
        data = blobs[i][1]
        checksums = {"md5": data.md5.hexdigest(),
                     "sha1": data.sha1.hexdigest(),
                     "sha256": data.sha256.hexdigest()}
        res[blobs[i][0]] = (locations[i], data.bytes_read, checksums)

    return res


@utils.error_handler(error_map)
def load_from_store(uri, context):
    """Load file from store backend.

    :param uri: blob uri
    :param context: user context
    :return: file iterator
    """
    if uri.startswith("sql://"):
        return utils.BlobIterator(
            database_api.get_from_store(uri, context))
    return backend.get_from_backend(uri=uri, context=context)[0]


@utils.error_handler(error_map)
def delete_blob(uri, context):
    """Delete blob from backend store.

    :param uri: blob uri
    :param context: user context
    """
    if uri.startswith("sql://"):
        return database_api.delete_from_store(uri, context)
    return backend.delete_from_backend(uri, context)


def get_known_schemes():
    return list(backend.get_known_schemes()) + ['sql']


def read_data(flobj, limit=16777216):
    """Read data into memory from the file-like object.

    :param flobj: file-like object that contains data
    :param limit: max file size that can be read into memory
    :return: string with data from the object
    """
    bytes_read = 0
    data = b''
    for chunk in flobj:
        bytes_read += len(chunk)
        if bytes_read > limit:
            raise exception.RequestEntityTooLarge()
        data += chunk
    return data
