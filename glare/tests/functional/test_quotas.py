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


class TestStaticQuotas(base.TestArtifact):
    """Test static quota limits."""

    def setUp(self):
        base.functional.FunctionalTest.setUp(self)

        self.set_user('user1')
        self.glare_server.deployment_flavor = 'noauth'
        self.glare_server.max_uploaded_data = '1000'
        self.glare_server.max_artifact_number = '10'

        self.glare_server.enabled_artifact_types = 'images,' \
                                                   'heat_templates,' \
                                                   'murano_packages,' \
                                                   'sample_artifact'
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')
        self.glare_server.artifact_type_section = """
[artifact_type:sample_artifact]
default_store = database
max_uploaded_data = 300
[artifact_type:images]
max_uploaded_data = 1500
max_artifact_number = 3
[artifact_type:heat_templates]
max_artifact_number = 15
[artifact_type:murano_packages]
max_uploaded_data = 1000
max_artifact_number = 10
"""
        self.start_servers(**self.__dict__.copy())

    def test_count_artifact_number(self):
        # initially there are no artifacts
        result = self.get('/all')
        self.assertEqual([], result['all'])

        # create 3 images for user1
        for i in range(3):
            img = self.create_artifact(
                data={'name': 'img%d' % i}, type_name='images')

        # creation of another image fails because of artifact type limit
        self.create_artifact(
            data={'name': 'img4'}, type_name='images', status=403)

        # create 7 murano packages
        for i in range(7):
            self.create_artifact(
                data={'name': 'mp%d' % i}, type_name='murano_packages')

        # creation of another package fails because of global limit
        self.create_artifact(
            data={'name': 'mp8'}, type_name='murano_packages', status=403)

        # delete an image and create another murano package work
        self.delete('/images/%s' % img['id'])
        self.create_artifact(
            data={'name': 'mp8'}, type_name='murano_packages')

        # admin can create his own artifacts
        self.set_user('admin')
        for i in range(10):
            self.create_artifact(
                data={'name': 'ht%d' % i}, type_name='heat_templates')

        # creation of another heat template fails because of global limit
        self.create_artifact(
            data={'name': 'ht11'}, type_name='heat_templates', status=403)

    def test_calculate_uploaded_data(self):
        headers = {'Content-Type': 'application/octet-stream'}

        # initially there are no artifacts
        result = self.get('/all')
        self.assertEqual([], result['all'])

        # create 2 sample artifacts for user1
        art1 = self.create_artifact(data={'name': 'art1'})
        art2 = self.create_artifact(data={'name': 'art2'})

        # create 2 images for user1
        img1 = self.create_artifact(data={'name': 'img1'}, type_name='images')
        img2 = self.create_artifact(data={'name': 'img2'}, type_name='images')

        # upload to art1 fails now because of type limit
        data = 'a' * 301
        self.put(url='/sample_artifact/%s/blob' % art1['id'],
                 data=data,
                 status=413,
                 headers=headers)

        # upload to img1 fails now because of global limit
        data = 'a' * 1001
        self.put(url='/images/%s/image' % img1['id'],
                 data=data,
                 status=413,
                 headers=headers)

        # upload 300 bytes to 'blob' of art1
        data = 'a' * 300
        self.put(url='/sample_artifact/%s/blob' % art1['id'],
                 data=data,
                 headers=headers)

        # upload another blob to art1 fails because of type limit
        self.put(url='/sample_artifact/%s/dict_of_blobs/blob' % art1['id'],
                 data='a',
                 status=413,
                 headers=headers)

        # upload to art2 fails now because of type limit
        self.put(url='/sample_artifact/%s/dict_of_blobs/blob' % art2['id'],
                 data='a',
                 status=413,
                 headers=headers)

        # delete art1 and check that upload to art2 works
        data = 'a' * 300
        self.delete('/sample_artifact/%s' % art1['id'])
        self.put(url='/sample_artifact/%s/dict_of_blobs/blob' % art2['id'],
                 data=data,
                 headers=headers)

        # upload 700 bytes to img1 works
        data = 'a' * 700
        self.put(url='/images/%s/image' % img1['id'],
                 data=data,
                 headers=headers)

        # upload to img2 fails because of global limit
        self.put(url='/images/%s/image' % img2['id'],
                 data='a',
                 status=413,
                 headers=headers)

        # admin can upload data to his images
        self.set_user('admin')
        img1 = self.create_artifact(data={'name': 'img1'}, type_name='images')
        data = 'a' * 1000
        self.put(url='/images/%s/image' % img1['id'],
                 data=data,
                 headers=headers)
