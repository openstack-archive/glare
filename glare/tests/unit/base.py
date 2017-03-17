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

import os
import shutil
import uuid

import fixtures
import glance_store as store
from glance_store import location
import jsonpatch
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_policy import policy as os_policy
import testtools

from glare.api.middleware import context
from glare.common import config
from glare.common import policy
from glare.common import utils
from glare.common import wsgi
from glare import locking
from glare.objects import base
from glare.tests.unit import simple_db_api

CONF = cfg.CONF

users = {
    'user1': {
        'id': str(uuid.uuid4()),
        'tenant_id': str(uuid.uuid4()),
        'token': str(uuid.uuid4()),
        'role': 'member'
    },
    'user2': {
        'id': str(uuid.uuid4()),
        'tenant_id': str(uuid.uuid4()),
        'token': str(uuid.uuid4()),
        'role': 'member'
    },
    'admin': {
        'id': str(uuid.uuid4()),
        'tenant_id': str(uuid.uuid4()),
        'token': str(uuid.uuid4()),
        'role': 'admin'
    },
    'anonymous': {
        'id': None,
        'tenant_id': None,
        'token': None,
        'role': None
    }
}


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self._config_fixture = self.useFixture(cfg_fixture.Config())
        config.parse_args(args=[])

        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self.conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(self.conf_dir)

        base.BaseArtifact.db_api = simple_db_api.SimpleAPI()
        base.BaseArtifact.lock_engine = locking.LockEngine(
            simple_db_api.SimpleLockApi())

        self.policy_file = self._copy_data_file("policy.json", self.conf_dir)
        self.config(policy_file=self.policy_file, group='oslo_policy')

        enf = policy.init(use_conf=False)
        for default in enf.registered_rules.values():
            if default.name not in enf.rules:
                enf.rules[default.name] = default.check

        location.SCHEME_TO_CLS_MAP = {}
        self._create_stores()
        self.addCleanup(setattr, location, 'SCHEME_TO_CLS_MAP', dict())

        self.addCleanup(simple_db_api.reset)
        self.addCleanup(policy.reset)

    @staticmethod
    def _copy_data_file(file_name, dst_dir):
        src_file_name = os.path.join('glare/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def config(self, **kw):
        """
        Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.

        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.

        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        self._config_fixture.config(**kw)

    @staticmethod
    def policy(**new_rules):
        enf = policy.init(use_conf=False)
        for rule_name, rule_check_str in new_rules.items():
            enf.rules[rule_name] = os_policy.RuleDefault(
                rule_name, rule_check_str).check

    @staticmethod
    def get_fake_request(path='', method='POST', is_admin=False,
                         user=None, roles=None):
        if roles is None:
            roles = ['member']

        req = wsgi.Request.blank(path)
        req.method = method

        kwargs = {
            'user': user['id'],
            'tenant': user['tenant_id'],
            'roles': roles,
            'is_admin': is_admin,
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
    def init_database(data):
        simple_db_api.init_artifacts(data)

    @staticmethod
    def generate_json_patch(values):
        patch = jsonpatch.JsonPatch(values)
        tuple(map(patch._get_operation, patch.patch))
        return patch
