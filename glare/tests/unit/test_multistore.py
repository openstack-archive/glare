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

from glare import engine
from glare.objects.meta import registry
from glare.tests.unit import base


class TestMultistore(base.BaseTestCase):

    def test_multistore(self):
        types = {'images': 'swift',
                 'heat_templates': 'rbd', 'heat_environments': 'file',
                 'tosca_templates': 'sheepdog',
                 'murano_packages': 'vsphere',
                 'sample_artifact': 'database',
                 'hooks_artifact': 'database',
                 'unpacking_artifact': 'database',
                 'non_nullable_fields_artifact': 'database'}

        # create engine and register new artifact types
        engine.Engine()

        for type_name, store in types.items():
            self.config(default_store=store,
                        group='artifact_type:' + type_name)

        for t in registry.ArtifactRegistry.obj_classes().values():
            name = t[0].get_type_name()
            if name == 'all':
                continue
            self.assertEqual(
                getattr(base.CONF, 'artifact_type:' + name).default_store,
                types[name])
