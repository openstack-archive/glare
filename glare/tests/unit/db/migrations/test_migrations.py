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

"""
Tests for database migrations. There are "opportunistic" tests for both mysql
and postgresql in here, which allows testing against these databases in a
properly configured unit test environment.
For the opportunistic testing you need to set up a db named 'openstack_citest'
with user 'openstack_citest' and password 'openstack_citest' on localhost.
The test will then use that db and u/p combo to run the tests.
For postgres on Ubuntu this can be done with the following commands:
::
 sudo -u postgres psql
 postgres=# create user openstack_citest with createdb login password
      'openstack_citest';
 postgres=# create database openstack_citest with owner openstack_citest;
"""

import contextlib

from alembic import script
import mock
from oslo_db.sqlalchemy import utils as db_utils
from oslo_db.tests.sqlalchemy import base as test_base
from oslo_log import log as logging
import sqlalchemy
import sqlalchemy.exc

from glare.db.migration import migration
import glare.db.sqlalchemy.api
from glare.tests.unit import glare_fixtures

LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def patch_with_engine(engine):
    with mock.patch.object(glare.db.sqlalchemy.api,
                           'get_engine') as patch_engine:
        patch_engine.return_value = engine
        yield


class WalkVersionsMixin(object):
    def _walk_versions(self, engine=None, alembic_cfg=None):
        # Determine latest version script from the repo, then
        # upgrade from 1 through to the latest, with no data
        # in the databases. This just checks that the schema itself
        # upgrades successfully.

        # Place the database under version control
        with patch_with_engine(engine):

            script_directory = script.ScriptDirectory.from_config(alembic_cfg)

            self.assertIsNone(self.migration_api.version(engine))

            versions = [ver for ver in script_directory.walk_revisions()]

            for version in reversed(versions):
                with glare_fixtures.BannedDBSchemaOperations():
                    self._migrate_up(engine, alembic_cfg,
                                     version.revision, with_data=True)

            for version in versions:
                with glare_fixtures.BannedDBSchemaOperations():
                    self._migrate_down(engine, alembic_cfg,
                                       version.down_revision, with_data=True)

    def _migrate_up(self, engine, config, version, with_data=False):
        """migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _pre_upgrade_### and
        _check_### functions in the main test.
        """
        try:
            if with_data:
                data = None
                pre_upgrade = getattr(
                    self, "_pre_upgrade_%s" % version, None)
                if pre_upgrade:
                    data = pre_upgrade(engine)

            self.migration_api.upgrade(version, config=config)
            self.assertEqual(version, self.migration_api.version(engine))
            if with_data:
                check = getattr(self, "_check_%s" % version, None)
                if check:
                    check(engine, data)
        except Exception:
            LOG.error("Failed to migrate to version %(version)s on engine "
                      "%(engine)s", {'version': version, 'engine': engine})
            raise

    def _migrate_down(self, engine, config, version, with_data=False):
        try:
            self.migration_api.downgrade(version, config=config)
            if with_data:
                post_downgrade = getattr(
                    self, "_post_downgrade_%s" % version, None)
                if post_downgrade:
                    post_downgrade(engine)
        except Exception:
            LOG.error("Failed to migrate to version %(version)s on engine "
                      "%(engine)s", {'version': version, 'engine': engine})
            raise


class GlareMigrationsCheckers(object):

    def setUp(self):
        super(GlareMigrationsCheckers, self).setUp()
        self.config = migration.get_alembic_config()
        self.migration_api = migration

    def assert_table(self, engine, table_name, indices, columns):
        table = db_utils.get_table(engine, table_name)
        index_data = [(index.name, index.columns.keys()) for index in
                      table.indexes]
        column_data = [column.name for column in table.columns]
        self.assertItemsEqual(columns, column_data)
        self.assertItemsEqual(indices, index_data)

    def test_walk_versions(self):
        self._walk_versions(self.engine, self.config)

    def _pre_upgrade_001(self, engine):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'glare_artifacts')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'glare_artifact_tags')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'glare_artifact_properties')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'glare_artifact_blobs')
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          db_utils.get_table, engine,
                          'glare_artifact_locks')

    def _check_001(self, engine, data):
        artifacts_indices = [('ix_glare_artifact_name_and_version',
                              ['name', 'version_prefix', 'version_suffix']),
                             ('ix_glare_artifact_type',
                              ['type_name']),
                             ('ix_glare_artifact_status', ['status']),
                             ('ix_glare_artifact_visibility', ['visibility']),
                             ('ix_glare_artifact_owner', ['owner'])]
        artifacts_columns = ['id',
                             'name',
                             'type_name',
                             'version_prefix',
                             'version_suffix',
                             'version_meta',
                             'description',
                             'visibility',
                             'status',
                             'owner',
                             'created_at',
                             'updated_at',
                             'activated_at']
        self.assert_table(engine, 'glare_artifacts', artifacts_indices,
                          artifacts_columns)

        tags_indices = [('ix_glare_artifact_tags_artifact_id',
                         ['artifact_id']),
                        ('ix_glare_artifact_tags_artifact_id_tag_value',
                         ['artifact_id',
                          'value'])]
        tags_columns = ['id',
                        'artifact_id',
                        'value']
        self.assert_table(engine, 'glare_artifact_tags', tags_indices,
                          tags_columns)

        prop_indices = [
            ('ix_glare_artifact_properties_artifact_id',
             ['artifact_id']),
            ('ix_glare_artifact_properties_name', ['name'])]
        prop_columns = ['id',
                        'artifact_id',
                        'name',
                        'string_value',
                        'int_value',
                        'numeric_value',
                        'bool_value',
                        'key_name',
                        'position']
        self.assert_table(engine, 'glare_artifact_properties', prop_indices,
                          prop_columns)

        blobs_indices = [
            ('ix_glare_artifact_blobs_artifact_id', ['artifact_id']),
            ('ix_glare_artifact_blobs_name', ['name'])]
        blobs_columns = ['id',
                         'artifact_id',
                         'size',
                         'md5',
                         'sha1',
                         'sha256',
                         'name',
                         'key_name',
                         'external',
                         'status',
                         'content_type',
                         'url']
        self.assert_table(engine, 'glare_artifact_blobs', blobs_indices,
                          blobs_columns)

        locks_indices = []
        locks_columns = ['id']
        self.assert_table(engine, 'glare_artifact_locks', locks_indices,
                          locks_columns)

    def _check_002(self, engine, data):
        locks_indices = []
        locks_columns = ['id', 'acquired_at']
        self.assert_table(engine, 'glare_artifact_locks', locks_indices,
                          locks_columns)

    def _check_003(self, engine, data):
        locks_indices = []
        locks_columns = ['id', 'data']
        self.assert_table(engine, 'glare_blob_data', locks_indices,
                          locks_columns)

    def _check_004(self, engine, data):
        quota_indices = []
        quota_columns = ['project_id',
                         'quota_name',
                         'quota_value']
        self.assert_table(engine, 'glare_quotas', quota_indices,
                          quota_columns)

    def _check_005(self, engine, data):
        artifacts_indices = [('ix_glare_artifact_name_and_version',
                              ['name', 'version_prefix', 'version_suffix']),
                             ('ix_glare_artifact_type',
                              ['type_name']),
                             ('ix_glare_artifact_status', ['status']),
                             ('ix_glare_artifact_visibility', ['visibility']),
                             ('ix_glare_artifact_owner', ['owner']),
                             ('ix_glare_artifact_display_name',
                              ['display_type_name'])]
        artifacts_columns = ['id',
                             'name',
                             'type_name',
                             'version_prefix',
                             'version_suffix',
                             'version_meta',
                             'description',
                             'visibility',
                             'status',
                             'owner',
                             'created_at',
                             'updated_at',
                             'activated_at',
                             'display_type_name']
        self.assert_table(engine, 'glare_artifacts', artifacts_indices,
                          artifacts_columns)


class TestMigrationsMySQL(GlareMigrationsCheckers,
                          WalkVersionsMixin,
                          test_base.MySQLOpportunisticTestCase):
    pass


class TestMigrationsPostgreSQL(GlareMigrationsCheckers,
                               WalkVersionsMixin,
                               test_base.PostgreSQLOpportunisticTestCase):
    pass


class TestMigrationsSqlite(GlareMigrationsCheckers,
                           WalkVersionsMixin,
                           test_base.DbTestCase,):
    pass
