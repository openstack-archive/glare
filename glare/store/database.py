# Copyright 2017 OpenStack Foundation.
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

from glare.db.sqlalchemy import api as db_api
from glare.store import base_api


class DatabaseStoreAPI(base_api.BaseStoreAPI):
    """Class that stores all data in sql database."""

    def add_to_backend(self, blob_id, data, context, verifier=None):
        session = db_api.get_session()
        return db_api.save_blob_data(context, blob_id, data, session)

    def add_to_backend_batch(self, blobs, context, verifier=None):
        session = db_api.get_session()
        return db_api.save_blob_data_batch(context, blobs, session)

    def get_from_store(self, uri, context):
        session = db_api.get_session()
        return db_api.get_blob_data(context, uri, session)

    def delete_from_store(self, uri, context):
        session = db_api.get_session()
        return db_api.delete_blob_data(context, uri, session)
