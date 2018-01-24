# Copyright 2017 - Red Hat
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from glare.common import exception as exc
from glare.tests.unit import base


class TestArtifactShow(base.BaseTestArtifactAPI):

    def test_show_basic(self):
        # Create an artifact and get its info back
        vals = {'name': 'art1', 'version': '0.0.1', 'string_required': 'str1',
                'int1': 5, 'float1': 5.0, 'bool1': 'yes'}
        art = self.controller.create(self.req, 'sample_artifact', vals)

        # Read info about created artifact
        show_art = self.controller.show(self.req, 'sample_artifact', art['id'])

        self.assertEqual(art, show_art)

        # Test that the artifact is not accessible from other non-metatype type
        self.assertRaises(exc.ArtifactNotFound,
                          self.controller.show, self.req, 'images', art['id'])

        # Test that the artifact is accessible from 'all' metatype
        show_art = self.controller.show(self.req, 'all', art['id'])

        self.assertEqual(art['id'], show_art['id'])

    def test_show_basic_negative(self):
        # If there is no artifact with given id glare raises ArtifactNotFound
        self.assertRaises(
            exc.ArtifactNotFound,
            self.controller.show, self.req, 'images', 'wrong_id')

        # If there is no artifact type glare raises TypeNotFound
        self.assertRaises(
            exc.TypeNotFound,
            self.controller.show, self.req, 'wrong_type', 'wrong_id')
