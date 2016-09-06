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

"""Common database interface for all objects"""


class BaseDBAPI(object):

    def __init__(self, cls):
        self.type = cls.get_type_name()
        self.cls = cls

    def create(self, context, values):
        """Create new artifact in db and return dict of values to the user

        :param context: user context
        :param values: dict of values that needs to be saved to db
        :return: dict of created values
        """
        raise NotImplementedError()

    def update(self, context, artifact_id, values):
        """Update artifact values in database

        :param artifact_id: id of artifact that needs to be updated
        :param context: user context
        :param values: values that needs to be updated
        :return: dict of updated artifact values
        """
        raise NotImplementedError()

    def get(self, context, artifact_id):
        """Return artifact values from database

        :param context: user context
        :param artifact_id: id of the artifact
        :return: dict of artifact values
        """
        raise NotImplementedError()

    def delete(self, context, artifact_id):
        """Delete artifacts from db

        :param context: user context
        :param artifact_id: id of artifact that needs to be deleted
        :return: dict for deleted artifact value
        """
        raise NotImplementedError()

    def list(self, context, filters, marker, limit, sort, latest):
        """List artifacts from db

        :param context: user request context
        :param filters: filter conditions from url
        :param marker: id of first artifact where we need to start
        artifact lookup
        :param limit: max number of items in list
        :param sort: sort conditions
        :param latest: flag that indicates, that only artifacts with highest
        versions should be returned in output
        :return: list of artifacts. Each artifact is represented as dict of
        values.
        """
        raise NotImplementedError()
