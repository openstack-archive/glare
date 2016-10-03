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

"""Database API for all artifact types"""

import six

from glare.db import api as base_api
from glare.db.sqlalchemy import api
from glare import locking


class ArtifactAPI(base_api.BaseDBAPI):

    def _serialize_values(self, values):
        new_values = {}
        if 'tags' in values:
            new_values['tags'] = values.pop('tags')
        for key, value in six.iteritems(values):
            if key in api.BASE_ARTIFACT_PROPERTIES:
                new_values[key] = value
            elif self.cls.is_blob(key) or self.cls.is_blob_dict(key):
                new_values.setdefault('blobs', {})[key] = value
            else:
                new_values.setdefault('properties', {})[key] = value
        return new_values

    def create(self, context, values):
        values = self._serialize_values(values)
        values['type_name'] = self.type
        session = api.get_session()
        return api.create(context, values, session)

    def update(self, context, artifact_id, values):
        session = api.get_session()
        return api.update(context, artifact_id,
                          self._serialize_values(values), session)

    def delete(self, context, artifact_id):
        session = api.get_session()
        return api.delete(context, artifact_id, session)

    def get(self, context, artifact_id):
        session = api.get_session()
        return api.get(context, artifact_id, session)

    def list(self, context, filters, marker, limit, sort, latest):
        session = api.get_session()
        if self.type != 'all':
            filters.append(('type_name', None, 'eq', None, self.type))
        return api.get_all(context=context, session=session, filters=filters,
                           marker=marker, limit=limit, sort=sort,
                           latest=latest)


class ArtifactLockApi(locking.LockApiBase):
    def create_lock(self, context, lock_key):
        session = api.get_session()
        return api.create_lock(context, lock_key, session)

    def delete_lock(self, context, lock_id):
        session = api.get_session()
        api.delete_lock(context, lock_id, session)
