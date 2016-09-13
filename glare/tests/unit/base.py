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

import fixtures
import glance_store as store
from glance_store import location
from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_db import options
from oslo_serialization import jsonutils
import testtools

from glare.common import config
from glare.common import utils

CONF = cfg.CONF


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()

        self._config_fixture = self.useFixture(cfg_fixture.Config())
        config.parse_args(args=[])
        self.addCleanup(CONF.reset)
        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self.conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(self.conf_dir)
        self.set_policy()

    def set_policy(self):
        conf_file = "policy.json"
        self.policy_file = self._copy_data_file(conf_file, self.conf_dir)
        self.config(policy_file=self.policy_file, group='oslo_policy')

    def _copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glare/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def set_property_protection_rules(self, rules):
        with open(self.property_file, 'w') as f:
            for rule_key in rules.keys():
                f.write('[%s]\n' % rule_key)
                for operation in rules[rule_key].keys():
                    roles_str = ','.join(rules[rule_key][operation])
                    f.write('%s = %s\n' % (operation, roles_str))

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


class StoreClearingUnitTest(BaseTestCase):

    def setUp(self):
        super(StoreClearingUnitTest, self).setUp()
        # Ensure stores + locations cleared
        location.SCHEME_TO_CLS_MAP = {}

        self._create_stores()
        self.addCleanup(setattr, location, 'SCHEME_TO_CLS_MAP', dict())

    def _create_stores(self, passing_config=True):
        """Create known stores. Mock out sheepdog's subprocess dependency
        on collie.

        :param passing_config: making store driver passes basic configurations.
        :returns: the number of how many store drivers been loaded.
        """
        store.register_opts(CONF)

        self.config(default_store='filesystem',
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        store.create_stores(CONF)


class IsolatedUnitTest(StoreClearingUnitTest):

    """
    Unit test case that establishes a mock environment within
    a testing directory (in isolation)
    """
    registry = None

    def setUp(self):
        super(IsolatedUnitTest, self).setUp()
        options.set_defaults(CONF, connection='sqlite:////%s/tests.sqlite' %
                                              self.test_dir)
        lockutils.set_defaults(os.path.join(self.test_dir))

        self.config(debug=False)

        self.config(default_store='filesystem',
                    filesystem_store_datadir=self.test_dir,
                    group="glance_store")

        store.create_stores()

    def set_policy_rules(self, rules):
        fap = open(CONF.oslo_policy.policy_file, 'w')
        fap.write(jsonutils.dumps(rules))
        fap.close()
