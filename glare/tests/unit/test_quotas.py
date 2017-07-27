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

from six import BytesIO

from glare.common import exception
from glare.tests.unit import base


class TestStaticQuotas(base.BaseTestArtifactAPI):
    """Test static quota limits."""

    def test_count_artifact_number(self):
        user1_req = self.get_fake_request(self.users['user1'])
        user2_req = self.get_fake_request(self.users['user2'])
        # initially there are no artifacts
        self.assertEqual(
            0, len(self.controller.list(user1_req, 'all')['artifacts']))
        self.assertEqual(
            0, len(self.controller.list(user2_req, 'all')['artifacts']))

        # set global limit on 10 artifacts
        self.config(max_artifact_number=10)
        # 3 images, 15 heat templates, 10 murano packages
        self.config(max_artifact_number=3,
                    group='artifact_type:images')
        self.config(max_artifact_number=15,
                    group='artifact_type:heat_templates')
        self.config(max_artifact_number=10,
                    group='artifact_type:murano_packages')

        # create 3 images for user1
        for i in range(3):
            img = self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i})

        # creation of another image fails because of artifact type limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'img4'})

        # create 7 murano packages
        for i in range(7):
            self.controller.create(
                user1_req, 'murano_packages', {'name': 'mp%d' % i})

        # creation of another package fails because of global limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'murano_packages', {'name': 'mp8'})

        # delete an image and create another murano package work
        self.controller.delete(user1_req, 'images', img['id'])
        self.controller.create(user1_req, 'murano_packages', {'name': 'mp8'})

        # user2 can create his own artifacts
        for i in range(10):
            self.controller.create(
                user2_req, 'heat_templates', {'name': 'ht%d' % i})

        # creation of another heat template fails because of global limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user2_req, 'heat_templates', {'name': 'ht11'})

        # disable global limit and try to create 15 heat templates
        self.config(max_artifact_number=-1)
        for i in range(15):
            self.controller.create(
                user1_req, 'heat_templates', {'name': 'ht%d' % i})

        # creation of another heat template fails because of type limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'heat_templates', {'name': 'ht16'})

        # disable type limit for heat templates and create 1 heat templates
        self.config(max_artifact_number=-1,
                    group='artifact_type:heat_templates')
        self.controller.create(
            user1_req, 'heat_templates', {'name': 'ht16'})

    def test_calculate_uploaded_data(self):
        user1_req = self.get_fake_request(self.users['user1'])
        user2_req = self.get_fake_request(self.users['user2'])
        # initially there are no artifacts
        self.assertEqual(
            0, len(self.controller.list(user1_req, 'all')['artifacts']))
        self.assertEqual(
            0, len(self.controller.list(user2_req, 'all')['artifacts']))

        # set global limit on 1000 bytes
        self.config(max_uploaded_data=1000)
        # 300 for sample artifact, 1500 for images, 1000 for murano packages
        self.config(max_uploaded_data=300,
                    group='artifact_type:sample_artifact')
        self.config(max_uploaded_data=1500,
                    group='artifact_type:images')
        self.config(max_uploaded_data=1000,
                    group='artifact_type:murano_packages')

        # create 2 sample artifacts for user 1
        art1 = self.controller.create(
            user1_req, 'sample_artifact', {'name': 'art1'})
        art2 = self.controller.create(
            user1_req, 'sample_artifact', {'name': 'art2'})

        # create 3 images for user1
        img1 = self.controller.create(
            user1_req, 'images', {'name': 'img1'})
        img2 = self.controller.create(
            user1_req, 'images', {'name': 'img2'})
        img3 = self.controller.create(
            user1_req, 'images', {'name': 'img3'})

        # upload to art1 fails now because of type limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'sample_artifact', art1['id'], 'blob',
            BytesIO(b'a' * 301), 'application/octet-stream', 301)

        # upload to img1 fails now because of global limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', img1['id'], 'image',
            BytesIO(b'a' * 1001), 'application/octet-stream', 1001)

        # upload 300 bytes to 'blob' of art1
        self.controller.upload_blob(
            user1_req, 'sample_artifact', art1['id'], 'blob',
            BytesIO(b'a' * 300), 'application/octet-stream',
            content_length=300)

        # upload another blob to art1 fails because of type limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'sample_artifact', art1['id'],
            'dict_of_blobs/blob', BytesIO(b'a'),
            'application/octet-stream', 1)

        # upload to art2 fails now because of type limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'sample_artifact', art2['id'], 'blob',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # delete art1 and check that upload to art2 works
        self.controller.delete(user1_req, 'sample_artifact', art1['id'])
        self.controller.upload_blob(
            user1_req, 'sample_artifact', art2['id'], 'blob',
            BytesIO(b'a' * 300), 'application/octet-stream', 300)

        # upload 700 bytes to img1 works
        self.controller.upload_blob(
            user1_req, 'images', img1['id'], 'image',
            BytesIO(b'a' * 700), 'application/octet-stream', 700)

        # upload to img2 fails because of global limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', img2['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # user2 can upload data to images
        img1 = self.controller.create(
            user2_req, 'images', {'name': 'img1'})
        self.controller.upload_blob(
            user2_req, 'images', img1['id'], 'image',
            BytesIO(b'a' * 1000), 'application/octet-stream', 1000)

        # disable global limit and try upload data from user1 again
        self.config(max_uploaded_data=-1)
        self.controller.upload_blob(
            user1_req, 'images', img2['id'], 'image',
            BytesIO(b'a' * 800), 'application/octet-stream', 800)

        # uploading more fails because of image type limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', img3['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # disable type limit and try upload data from user1 again
        self.config(max_uploaded_data=-1, group='artifact_type:images')
        self.controller.upload_blob(
            user1_req, 'images', img3['id'], 'image',
            BytesIO(b'a' * 1000), 'application/octet-stream', 1000)
