# Copyright 2017 - Nokia Networks
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

from glare.tests.functional import base


class TestVisibility(base.TestArtifact):

    """Test Glare artifact visibility for various users."""

    def test_visibility_basic(self):

        self.set_user('user1')
        art1 = self.create_artifact(data={'name': 'art1', 'version': 1.0})
        url = '/sample_artifact/%s' % art1['id']

        # Artifact is visible by its owner
        self.get(url=url)

        # Owner can modify the artifact
        patch = [{"op": "replace", "path": "/description", "value": "dd"}]
        self.patch(url=url, data=patch)

        # Artifact is not visible by another user
        self.set_user('user2')
        self.get(url=url, status=404)

        # Artifact is visible by admin
        self.set_user('admin')
        self.get(url=url)

        # Admin can update the artifact
        patch = [{"op": "replace", "path": "/string_required", "value": "gg"}]
        self.patch(url=url, data=patch)

        # Activate and publish the artifact
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public)

        # All users can see public artifact

        self.set_user('user1')
        self.get(url=url)

        # Default policy 'update_public' forbids the owner to update public
        # artifacts
        patch = [{"op": "replace", "path": "/description", "value": "bb"}]
        self.patch(url=url, data=patch, status=403)

        self.set_user('admin')
        self.get(url=url)

        # Admin can always update public artifacts
        patch = [{"op": "replace", "path": "/description", "value": "ss"}]
        self.patch(url=url, data=patch)

        self.set_user('user2')
        self.get(url=url)

        # Regular user cannot update public artifact
        patch = [{"op": "replace", "path": "/description", "value": "aa"}]
        self.patch(url=url, data=patch, status=403)

    def test_visibility_name_version(self):
        self.set_user('user1')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0})

        # User can't create another artifact with the same name/version
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             status=409)

        art2 = self.create_artifact(data={'name': 'your_art', 'version': 2.0})
        url = '/sample_artifact/%s' % art2['id']

        # User can't change name and version if such artifact already exists
        patch = [
            {"op": "replace", "path": "/name", "value": "my_art"},
            {"op": "replace", "path": "/version", "value": 1.0}
        ]
        self.patch(url=url, data=patch, status=409)

        # Another user can create an artifact with the same name/version
        self.set_user("user2")
        art3 = self.create_artifact(data={'name': 'my_art', 'version': 1.0})

        # Now admin sees 2 artifacts with the same name/version
        self.set_user("admin")
        url = '/sample_artifact?name=my_art&version=1'
        self.assertEqual(2, len(self.get(url=url)['artifacts']))

        # Admin can activate and publish artifact art3
        url = '/sample_artifact/%s' % art3['id']
        patch = [{"op": "replace", "path": "/string_required", "value": "gg"}]
        self.patch(url=url, data=patch)
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public)

        # After that user1 sees 2 artifacts with the same name/version as well
        self.set_user("user1")
        url = '/sample_artifact?name=my_art&version=1'
        self.assertEqual(2, len(self.get(url=url)['artifacts']))

        # User2 still sees only his public artifact
        self.set_user("user2")
        url = '/sample_artifact?name=my_art&version=1'
        self.assertEqual(1, len(self.get(url=url)['artifacts']))

        # Admin is able to create a private artifact with the same name/version
        self.set_user("admin")
        art4 = self.create_artifact(data={'name': 'my_art', 'version': 1.0})

        # And he sees 3 artifacts
        url = '/sample_artifact?name=my_art&version=1'
        self.assertEqual(3, len(self.get(url=url)['artifacts']))

        # But he can't publish his artifact, because this name/version already
        # exists in public scope
        url = '/sample_artifact/%s' % art4['id']
        patch = [{"op": "replace", "path": "/string_required", "value": "gg"}]
        self.patch(url=url, data=patch)
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public, status=409)

        # Admin publishes artifact art2
        url = '/sample_artifact/%s' % art2['id']
        patch = [{"op": "replace", "path": "/string_required", "value": "gg"}]
        self.patch(url=url, data=patch)
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public)

        # User2 can create his own private artifact with the same name/version
        self.set_user("user2")
        self.create_artifact(data={'name': 'your_art', 'version': 2.0})

    def test_visibility_artifact_types(self):
        self.set_user('user1')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             type_name='images')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             type_name='heat_templates')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             type_name='heat_environments')

    def test_visibility_all(self):
        self.set_user('user1')
        art1 = self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                                    type_name='images')
        art2 = self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                                    type_name='sample_artifact')
        # User 1 sees his 2 artifacts
        url = '/all?name=my_art&version=1'
        self.assertEqual(2, len(self.get(url=url)['artifacts']))

        self.set_user('user2')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             type_name='images')
        self.create_artifact(data={'name': 'my_art', 'version': 1.0},
                             type_name='sample_artifact')
        # User 2 sees his 2 artifacts
        url = '/all?name=my_art&version=1'
        self.assertEqual(2, len(self.get(url=url)['artifacts']))

        # Admin sees 4 artifacts from both users
        self.set_user("admin")
        self.assertEqual(4, len(self.get(url=url)['artifacts']))

        # After publishing art1 and art2 user 2 can see 4 artifacts as well
        url = '/images/%s' % art1['id']
        patch = [
            {"op": "replace", "path": "/disk_format", "value": "iso"},
            {"op": "replace", "path": "/container_format", "value": "bare"}]
        self.patch(url=url, data=patch)
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public)

        url = '/sample_artifact/%s' % art2['id']
        patch = [{"op": "replace", "path": "/string_required", "value": "gg"}]
        self.patch(url=url, data=patch)
        self.patch(url=url, data=self.make_active)
        self.patch(url=url, data=self.make_public)

        self.set_user("user2")
        url = '/all?name=my_art&version=1'
        self.assertEqual(4, len(self.get(url=url)['artifacts']))
