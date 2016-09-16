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

import sqlalchemy
import testtools

from glare.common import exception
from glare.tests.unit import glare_fixtures


class TestBannedDBSchemaOperations(testtools.TestCase):
    def test_column(self):
        column = sqlalchemy.Column()
        with glare_fixtures.BannedDBSchemaOperations(['Column']):
            self.assertRaises(exception.DBNotAllowed,
                              column.drop)
            self.assertRaises(exception.DBNotAllowed,
                              column.alter)

    def test_table(self):
        table = sqlalchemy.Table()
        with glare_fixtures.BannedDBSchemaOperations(['Table']):
            self.assertRaises(exception.DBNotAllowed,
                              table.drop)
            self.assertRaises(exception.DBNotAllowed,
                              table.alter)
