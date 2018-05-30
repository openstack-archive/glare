# Copyright 2012 OpenStack Foundation.
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


import fixtures
import glance_store as store
from glance_store import location
import jsonpatch
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_policy import policy as os_policy
from oslo_utils import uuidutils
import testtools

from glare.api.middleware import context
from glare.api.v1 import resource
from glare.common import policy
from glare.common import wsgi
from glare.db.sqlalchemy import api as db_api

CONF = cfg.CONF


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self._config_fixture = self.useFixture(cfg_fixture.Config())

        self.users = {
            'user1': {
                'id': uuidutils.generate_uuid(),
                'tenant_id': uuidutils.generate_uuid(),
                'token': uuidutils.generate_uuid(),
                'roles': ['member']
            },
            'user2': {
                'id': uuidutils.generate_uuid(),
                'tenant_id': uuidutils.generate_uuid(),
                'token': uuidutils.generate_uuid(),
                'roles': ['member']
            },
            'admin': {
                'id': uuidutils.generate_uuid(),
                'tenant_id': uuidutils.generate_uuid(),
                'token': uuidutils.generate_uuid(),
                'roles': ['admin']
            },
            'anonymous': {
                'id': None,
                'tenant_id': None,
                'token': None,
                'roles': []
            }
        }

        self.test_dir = self.useFixture(fixtures.TempDir()).path

        CONF.set_default('connection', 'sqlite://', group='database')
        db_api.setup_db()

        enf = policy.init(use_conf=False)
        for default in enf.registered_rules.values():
            if default.name not in enf.rules:
                enf.rules[default.name] = default.check

        self.config(
            custom_artifact_types_modules=[
                'glare.tests.sample_artifact',
                'glare.tests.hooks_artifact',
                'glare.tests.unpacking_artifact',
                'glare.tests.non_nullable_fields_artifact'
            ],
            enabled_artifact_types=[
                'non_nullable_fields_artifact', 'unpacking_artifact',
                'hooks_artifact', 'sample_artifact',
                'images', 'heat_templates', 'heat_environments',
                'murano_packages', 'tosca_templates']
        )

        location.SCHEME_TO_CLS_MAP = {}
        self._create_stores()
        self.addCleanup(setattr, location, 'SCHEME_TO_CLS_MAP', dict())

        self.addCleanup(db_api.drop_db)
        self.addCleanup(policy.reset)

    def config(self, **kw):
        """Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        self._config_fixture.config(**kw)

    @staticmethod
    def policy(new_rules):
        enf = policy.init(use_conf=False)
        for rule_name, rule_check_str in new_rules.items():
            enf.rules[rule_name] = os_policy.RuleDefault(
                rule_name, rule_check_str).check

    @staticmethod
    def get_fake_request(user):
        req = wsgi.Request.blank('')
        req.method = 'POST'
        kwargs = {
            'user': user['id'],
            'tenant': user['tenant_id'],
            'roles': user['roles'],
            'is_admin': 'admin' in user['roles'],
        }
        req.context = context.RequestContext(**kwargs)
        return req

    def _create_stores(self):
        """Create known stores. Mock out sheepdog's subprocess dependency
        on collie.

        :returns: the number of how many store drivers been loaded.
        """
        store.register_opts(CONF)

        self.config(default_store='filesystem',
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        store.create_stores(CONF)

    @staticmethod
    def generate_json_patch(values):
        patch = jsonpatch.JsonPatch(values)
        tuple(map(patch._get_operation, patch.patch))
        return patch

    def update_with_values(self, values, exc_class=None,
                           art_type='sample_artifact', art_id=None):
        patch = self.generate_json_patch(values)
        art_id = art_id or self.sample_artifact['id']
        if exc_class is None:
            return self.controller.update(self.req, art_type, art_id, patch)
        else:
            self.assertRaises(exc_class, self.controller.update, self.req,
                              art_type, art_id, patch)


class BaseTestArtifactAPI(BaseTestCase):

    def setUp(self):
        super(BaseTestArtifactAPI, self).setUp()
        self.controller = resource.ArtifactsController()
        self.req = self.get_fake_request(user=self.users['user1'])
        self.config(default_store='database',
                    group='artifact_type:sample_artifact')
