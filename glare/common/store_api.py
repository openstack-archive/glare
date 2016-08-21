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

import hashlib
import urllib

from glance_store import backend
from glance_store import exceptions as store_exc
from oslo_config import cfg
from oslo_log import log as logging
import six.moves.urllib.parse as urlparse

from glare.common import exception
from glare.common import utils
from glare.i18n import _

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

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
    :return: tuple of values: (location_uri, size, checksum, metadata)
    """
    (location, size, checksum, metadata) = backend.add_to_backend(
        CONF, blob_id,
        utils.LimitingReader(utils.CooperativeReader(blob), max_size),
        0, store_type, context, verifier)
    return location, size, checksum


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


@utils.error_handler(error_map)
def get_location_info(url, context, max_size, calc_checksum=True):
    """Validate location and get information about external blob

    :param url: blob url
    :param context: user context
    :param calc_checksum: define if checksum must be calculated
    :return: blob size and checksum
    """
    # validate uri
    scheme = urlparse.urlparse(url).scheme
    if scheme not in ('http', 'https'):
        msg = _("Location %s is invalid.") % url
        raise exception.BadRequest(message=msg)

    res = urllib.urlopen(url)
    http_message = res.info()
    content_type = getattr(http_message, 'type') or 'application/octet-stream'

    # calculate blob checksum to ensure that location blob won't be changed
    # in future
    # TODO(kairat) need to support external location signatures
    checksum = None
    size = 0
    if calc_checksum:
        checksum = hashlib.md5()
        blob_data = load_from_store(url, context)
        for buf in blob_data:
            checksum.update(buf)
            size += len(buf)
            if size > max_size:
                msg = _("External blob size %(size)d exceeds maximum allowed "
                        "size %(max)d."), {'size': size, 'max': max_size}
                raise exception.BadRequest(message=msg)
        checksum = checksum.hexdigest()
    else:
        # request blob size
        size = get_blob_size(url, context=context)
        if size < 0 or size > max_size:
            msg = _("Invalid blob size %d.") % size
            raise exception.BadRequest(message=msg)

    LOG.debug("Checksum %(checksum)s and size %(size)s calculated "
              "successfully for location %(location)s",
              {'checksum': str(checksum), 'size': str(size),
               'location': url})

    return size, checksum, content_type
