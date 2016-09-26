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

from glare.common import exception
from glare.common import utils

CONF = cfg.CONF

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
    """Save file to specified store type and return location info to the user

    :param store_type: type of the store, None means save to default store.
    :param blob_id: id of artifact
    :param blob: blob file iterator
    :param context: user context
    :param verifier:signature verified
    :return: tuple of values: (location_uri, size, checksums, metadata)
    """
    data = utils.LimitingReader(utils.CooperativeReader(blob), max_size)
    (location, size, md5checksum, metadata) = backend.add_to_backend(
        CONF, blob_id, data, 0, store_type, context, verifier)
    checksums = {"md5": md5checksum,
                 "sha1": data.sha1.hexdigest(),
                 "sha256": data.sha256.hexdigest()}
    return location, size, checksums


@utils.error_handler(error_map)
def load_from_store(uri, context):
    """Load file from store backend.

    :param uri: blob uri
    :param context: user context
    :return: file iterator
    """
    return backend.get_from_backend(uri=uri, context=context)[0]


@utils.error_handler(error_map)
def delete_blob(uri, context):
    """Delete blob from backend store

    :param uri: blob uri
    :param context: user context
    """
    return backend.delete_from_backend(uri, context)


@utils.error_handler(error_map)
def get_blob_size(uri, context):
    return backend.get_size_from_backend(uri, context)
