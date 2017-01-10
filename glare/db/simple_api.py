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


"""Simple Database API for testing artifact types"""

from oslo_log import log as logging
from oslo_utils import timeutils
import semantic_version
import six

import glare.common.exception as glare_exc
from glare.common import utils
from glare.db import api
from glare.i18n import _
from glare import locking


LOG = logging.getLogger(__name__)

DATA = {
    'artifacts': {},
    'locks': {}
}

error_map = [{"catch": KeyError, "raise": glare_exc.NotFound}]


class SimpleAPI(api.BaseDBAPI):

    @utils.error_handler(error_map)
    def create(self, context, values):
        global DATA
        values['created_at'] = values['updated_at'] = timeutils.utcnow()
        artifact_id = values['id']
        if artifact_id in DATA['artifacts']:
            msg = _("Artifact with id '%s' already exists") % artifact_id
            raise glare_exc.BadRequest(msg)
        values['type_name'] = self.type

        DATA['artifacts'][artifact_id] = values
        return values

    @utils.error_handler(error_map)
    def update(self, context, artifact_id, values):
        global DATA
        af = DATA['artifacts'][artifact_id]
        if af['owner'] != context.tenant and not context.is_admin:
            if af['visibility'] == 'private':
                raise glare_exc.BadRequest
            else:
                raise glare_exc.Forbidden
        af.update(values)
        for key, val in six.iteritems(values):
            if val is None:
                del af[key]
            else:
                af[key] = val
        if 'status' in values and values['status'] == self.cls.STATUS.ACTIVE:
            af['activated_at'] = timeutils.utcnow()
        af['updated_at'] = timeutils.utcnow()
        DATA['artifacts'][artifact_id] = af
        return af

    @utils.error_handler(error_map)
    def delete(self, context, artifact_id):
        global DATA
        af = DATA['artifacts'][artifact_id]
        if af['owner'] != context.tenant and not context.is_admin:
            if af['visibility'] == 'private':
                raise glare_exc.BadRequest
            else:
                raise glare_exc.Forbidden
        del DATA['artifacts'][artifact_id]

    @utils.error_handler(error_map)
    def get(self, context, artifact_id):
        global DATA
        af = DATA['artifacts'][artifact_id]
        if af['owner'] != context.tenant and \
                not context.is_admin and af['visibility'] == 'private':
            raise KeyError
        return af

    @utils.error_handler(error_map)
    def list(self, context, filters, marker, limit, sort, latest):
        global DATA
        afs = list(DATA['artifacts'].values())
        if self.type != 'all':
            filters.append(('type_name', None, 'eq', None, self.type))

        for field_name, key_name, op, field_type, value in filters:
            if field_name == 'tags':
                values = utils.split_filter_value_for_quotes(value)
                for af in afs[:]:
                    if not set(values).issubset(af['tags']):
                        afs.remove(af)
            elif field_name == 'tags-any':
                values = utils.split_filter_value_for_quotes(value)
                for af in afs[:]:
                    for tag in values:
                        if tag in af['tags']:
                            break
                    else:
                        afs.remove(af)
            # filter by dict field
            elif key_name is not None:
                for af in afs[:]:
                    if key_name not in af[field_name]:
                        afs.remove(af)
                    elif value is None:
                        continue
                    elif op == 'in':
                        for val in value:
                            if af[field_name][key_name] == val:
                                break
                        else:
                            afs.remove(af)
                    elif not utils.evaluate_filter_op(
                            af[field_name][key_name], op, value):
                        afs.remove(af)
            # filter by common field
            else:
                for af in afs[:]:
                    if op == 'in':
                        for val in value:
                            if field_name == 'version':
                                val = semantic_version.Version.coerce(val)
                                af_version = semantic_version.Version.coerce(
                                    af[field_name])
                                if af_version == val:
                                    break
                            elif af[field_name] == val:
                                break
                        else:
                            afs.remove(af)
                    else:
                        if field_name == 'version':
                            af_version = semantic_version.Version.coerce(
                                af[field_name])
                            if not utils.evaluate_filter_op(
                                    af_version, op,
                                    semantic_version.Version.coerce(value)):
                                afs.remove(af)
                        elif isinstance(af.get(field_name), list):
                            if value not in af[field_name]:
                                afs.remove(af)
                        elif not utils.evaluate_filter_op(
                                af[field_name], op, value):
                            afs.remove(af)

        if not context.is_admin:
            for af in afs[:]:
                if af['visibility'] != 'public' and \
                        af['owner'] != context.tenant:
                    afs.remove(af)

        if latest:
            afs.sort(cmp=version_cmp, reverse=True)
            afs.sort(key=lambda x: x['name'])
            new_afs = []
            new_afs_names = []
            for af in afs:
                if af['name'] not in new_afs_names:
                    new_afs_names.append(af['name'])
                    new_afs.append(af)
            afs = new_afs

        for key, dir, prop_type in reversed(sort):
            reverse = dir == 'desc'
            if key == 'version':
                afs.sort(cmp=version_cmp, reverse=reverse)
            else:
                afs.sort(key=lambda x: x.get(key, None), reverse=reverse)

        if marker:
            for af in afs[:]:
                afs.remove(af)
                if af['id'] == marker:
                    break

        if limit:
            afs = afs[:limit]

        return afs


def version_cmp(af1, af2):
    return semantic_version.compare(
        af1['version'], af2['version'])


class SimpleLockApi(locking.LockApiBase):
    def create_lock(self, context, lock_key):
        global DATA
        item_lock = DATA['locks'].get(lock_key)
        if item_lock:
            msg = _("Cannot lock an item with key %s. "
                    "Lock already acquired by other request.") % lock_key
            raise glare_exc.Conflict(msg)
            # TODO(kairat) Log user data in the log so we can identify who
            # acquired the lock
        else:
            DATA['locks'][lock_key] = lock_key
            return lock_key

    def delete_lock(self, context, lock_id):
        global DATA
        item_lock = DATA['locks'][lock_id]
        if item_lock:
            del DATA['locks'][lock_id]
