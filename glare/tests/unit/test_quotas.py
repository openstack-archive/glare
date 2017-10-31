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

import mock
from six import BytesIO

from glare.common import exception
from glare.common import store_api
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

    def test_max_artifact_number_change_global_config_values(self):
        user1_req = self.get_fake_request(self.users['user1'])
        # initially there are no artifacts
        self.assertEqual(
            0, len(self.controller.list(user1_req, 'all')['artifacts']))

        arts = []

        # set global limit on 5 artifacts
        self.config(max_artifact_number=5)

        # create 5 artifacts for user1
        for i in range(5):
            arts.append(self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i}))

        # creation of another image fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # increase the global limit to 10 artifacts
        self.config(max_artifact_number=10)

        # now user can create 5 new artifacts
        for i in range(5, 10):
            arts.append(self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i}))

        # creation of another image fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # decrease the global limit to 5 artifacts again
        self.config(max_artifact_number=5)

        # delete 5 artifacts
        for i in range(5):
            self.controller.delete(user1_req, 'images', arts[i]['id'])
        self.assertEqual(
            5, len(self.controller.list(user1_req, 'all')['artifacts']))

        # creation of another image still fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # deletion of another artifact should unblock image creation
        self.controller.delete(user1_req, 'images', arts[5]['id'])
        self.controller.create(user1_req, 'images', {'name': 'okay_img'})

    def test_max_artifact_number_change_type_config_values(self):
        user1_req = self.get_fake_request(self.users['user1'])
        # initially there are no artifacts
        self.assertEqual(
            0, len(self.controller.list(user1_req, 'all')['artifacts']))

        arts = []

        # set type limit on 5 artifacts
        self.config(max_artifact_number=5,
                    group='artifact_type:images')

        # create 5 artifacts for user1
        for i in range(5):
            arts.append(self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i}))

        # creation of another image fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # increase the type limit to 10 artifacts
        self.config(max_artifact_number=10,
                    group='artifact_type:images')

        # create 5 new artifacts
        for i in range(5, 10):
            arts.append(self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i}))

        # creation of another image fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # decrease the global limit to 5 artifacts again
        self.config(max_artifact_number=5,
                    group='artifact_type:images')

        # delete 5 artifacts
        for i in range(5):
            self.controller.delete(user1_req, 'images', arts[i]['id'])
        self.assertEqual(
            5, len(self.controller.list(user1_req, 'all')['artifacts']))

        # creation of another image still fails because of the limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'images', {'name': 'failed_img'})

        # deletion of another artifact should unblock image creation
        self.controller.delete(user1_req, 'images', arts[5]['id'])
        self.controller.create(user1_req, 'images', {'name': 'okay_img'})

    def test_max_uploaded_data_change_global_config_values(self):
        user1_req = self.get_fake_request(self.users['user1'])

        # set global limit on 1000 bytes
        self.config(max_uploaded_data=1000)

        arts = []

        # create 5 images for user1 and upload 200 bytes to each
        for i in range(5):
            art = self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i})
            art = self.controller.upload_blob(
                user1_req, 'images', art['id'], 'image',
                BytesIO(b'a' * 200), 'application/octet-stream', 200)
            arts.append(art)

        # now all uploads fail
        new_art = self.controller.create(
            user1_req, 'images', {'name': 'new_img'})
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # increase the global limit to 2000 bytes
        self.config(max_uploaded_data=2000)

        # now user can 5 new artifacts and upload 200 bytes to each
        for i in range(5, 10):
            art = self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i})
            art = self.controller.upload_blob(
                user1_req, 'images', art['id'], 'image',
                BytesIO(b'a' * 200), 'application/octet-stream', 200)
            arts.append(art)

        # new uploads still fail, because we reached the new limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # decrease the global limit to 1000 bytes again
        self.config(max_uploaded_data=1000)

        # delete 6 artifacts
        for i in range(6):
            self.controller.delete(user1_req, 'images', arts[i]['id'])
        self.assertEqual(
            5, len(self.controller.list(user1_req, 'all')['artifacts']))

        # now we can upload data to new_art
        self.controller.upload_blob(
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a' * 200), 'application/octet-stream', 200)

    def test_max_max_uploaded_data_change_type_config_values(self):
        user1_req = self.get_fake_request(self.users['user1'])

        # set type limit on 1000 bytes
        self.config(max_uploaded_data=1000,
                    group='artifact_type:images')

        arts = []

        # create 5 images for user1 and upload 200 bytes to each
        for i in range(5):
            art = self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i})
            art = self.controller.upload_blob(
                user1_req, 'images', art['id'], 'image',
                BytesIO(b'a' * 200), 'application/octet-stream', 200)
            arts.append(art)

        # now all uploads fail
        new_art = self.controller.create(
            user1_req, 'images', {'name': 'new_img'})
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # increase the type limit to 2000 bytes
        self.config(max_uploaded_data=2000,
                    group='artifact_type:images')

        # now user can 5 new artifacts and upload 200 bytes to each
        for i in range(5, 10):
            art = self.controller.create(
                user1_req, 'images', {'name': 'img%d' % i})
            art = self.controller.upload_blob(
                user1_req, 'images', art['id'], 'image',
                BytesIO(b'a' * 200), 'application/octet-stream', 200)
            arts.append(art)

        # new uploads still fail, because we reached the new limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # decrease the type limit to 1000 bytes again
        self.config(max_uploaded_data=1000,
                    group='artifact_type:images')

        # delete 6 artifacts
        for i in range(6):
            self.controller.delete(user1_req, 'images', arts[i]['id'])
        self.assertEqual(
            5, len(self.controller.list(user1_req, 'all')['artifacts']))

        # now we can upload data to new_art
        self.controller.upload_blob(
            user1_req, 'images', new_art['id'], 'image',
            BytesIO(b'a' * 200), 'application/octet-stream', 200)


class TestDynamicQuotas(base.BaseTestArtifactAPI):
    """Test dynamic quota limits."""

    def test_count_artifact_number(self):
        user1_req = self.get_fake_request(self.users['user1'])
        user2_req = self.get_fake_request(self.users['user2'])
        # initially there are no artifacts
        self.assertEqual(
            0, len(self.controller.list(user1_req, 'all')['artifacts']))
        self.assertEqual(
            0, len(self.controller.list(user2_req, 'all')['artifacts']))

        values = {
            user1_req.context.project_id: {
                "max_artifact_number:images": 3,
                "max_artifact_number:heat_templates": 15,
                "max_artifact_number:murano_packages": 10,
                "max_artifact_number": 10
            },
            user2_req.context.project_id: {
                "max_artifact_number": 10
            }
        }

        admin_req = self.get_fake_request(self.users["admin"])
        # define several quotas
        self.controller.set_quotas(admin_req, values)

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

        # disable global limit for user1 and try to create 15 heat templates
        values = {
            user1_req.context.project_id: {
                "max_artifact_number:images": 3,
                "max_artifact_number:heat_templates": 15,
                "max_artifact_number:murano_packages": 10,
                "max_artifact_number": -1
            }
        }
        self.controller.set_quotas(admin_req, values)

        for i in range(15):
            self.controller.create(
                user1_req, 'heat_templates', {'name': 'ht%d' % i})

        # creation of another heat template fails because of type limit
        self.assertRaises(exception.Forbidden, self.controller.create,
                          user1_req, 'heat_templates', {'name': 'ht16'})

        # disable type limit for heat templates and create 1 heat templates
        values = {
            user1_req.context.project_id: {
                "max_artifact_number:images": 3,
                "max_artifact_number:heat_templates": -1,
                "max_artifact_number:murano_packages": 10,
                "max_artifact_number": -1
            }
        }
        self.controller.set_quotas(admin_req, values)

        # now user1 can create another heat template
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

        values = {
            user1_req.context.project_id: {
                "max_uploaded_data:images": 1500,
                "max_uploaded_data:sample_artifact": 300,
                "max_uploaded_data:murano_packages": 1000,
                "max_uploaded_data": 1000
            },
            user2_req.context.project_id: {
                "max_uploaded_data": 1000
            }
        }

        admin_req = self.get_fake_request(self.users["admin"])
        # define several quotas
        self.controller.set_quotas(admin_req, values)
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
        values = {
            user1_req.context.project_id: {
                "max_uploaded_data:images": 1500,
                "max_uploaded_data:sample_artifact": 300,
                "max_uploaded_data:murano_packages": 1000,
                "max_uploaded_data": -1
            }
        }
        self.controller.set_quotas(admin_req, values)

        self.controller.upload_blob(
            user1_req, 'images', img2['id'], 'image',
            BytesIO(b'a' * 800), 'application/octet-stream', 800)

        # uploading more fails because of image type limit
        self.assertRaises(
            exception.RequestEntityTooLarge, self.controller.upload_blob,
            user1_req, 'images', img3['id'], 'image',
            BytesIO(b'a'), 'application/octet-stream', 1)

        # disable type limit and try upload data from user1 again
        values = {
            user1_req.context.project_id: {
                "max_uploaded_data:images": -1,
                "max_uploaded_data:sample_artifact": 300,
                "max_uploaded_data:murano_packages": 1000,
                "max_uploaded_data": -1
            }
        }
        self.controller.set_quotas(admin_req, values)
        self.controller.upload_blob(
            user1_req, 'images', img3['id'], 'image',
            BytesIO(b'a' * 1000), 'application/octet-stream', 1000)

    def test_quota_upload_no_content_length(self):
        user1_req = self.get_fake_request(self.users['user1'])
        user2_req = self.get_fake_request(self.users['user2'])
        admin_req = self.get_fake_request(self.users['admin'])

        values = {
            user1_req.context.project_id: {
                "max_uploaded_data:sample_artifact": 20,
                "max_uploaded_data": 5
            },
            user2_req.context.project_id: {
                "max_uploaded_data:sample_artifact": 7,
                "max_uploaded_data": -1
            },
            admin_req.context.project_id: {
                "max_uploaded_data:sample_artifact": -1,
                "max_uploaded_data": -1
            }
        }

        # define several quotas
        self.controller.set_quotas(admin_req, values)

        # create a sample artifacts for user 1
        art1 = self.controller.create(
            user1_req, 'sample_artifact', {'name': 'art1'})

        # Max small_blob size is 10. User1 global quota is 5.
        # Since user doesn't specify how many bytes he wants to upload,
        # engine can't verify it before upload. Therefore it allocates
        # 5 available bytes for user and begins upload. If uploaded data
        # amount exceeds this limit RequestEntityTooLarge is raised and
        # upload fails.
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 10)
            self.assertRaises(
                exception.RequestEntityTooLarge,
                self.controller.upload_blob,
                user1_req, 'sample_artifact', art1['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, user1_req.context, 5, store_type='database')

        # check that blob wasn't uploaded
        self.assertIsNone(
            self.controller.show(
                user1_req, 'sample_artifact', art1['id'])['small_blob'])

        # try to upload with smaller amount that doesn't exceeds quota
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 4)
            self.controller.upload_blob(
                user1_req, 'sample_artifact', art1['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, user1_req.context, 5, store_type='database')

        # check that blob was uploaded
        blob = self.controller.show(
            user1_req, 'sample_artifact', art1['id'])['small_blob']
        self.assertEqual(4, blob['size'])
        self.assertEqual('active', blob['status'])

        # create a sample artifacts for user 2
        art2 = self.controller.create(
            user2_req, 'sample_artifact', {'name': 'art2'})

        # Max small_blob size is 10. User1 has no global quota, but his
        # type quota is 7.
        # Since user doesn't specify how many bytes he wants to upload,
        # engine can't verify it before upload. Therefore it allocates
        # 7 available bytes for user and begins upload. If uploaded data
        # amount exceeds this limit RequestEntityTooLarge is raised and
        # upload fails.
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 10)
            self.assertRaises(
                exception.RequestEntityTooLarge,
                self.controller.upload_blob,
                user2_req, 'sample_artifact', art2['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, user2_req.context, 7, store_type='database')

        # check that blob wasn't uploaded
        self.assertIsNone(
            self.controller.show(
                user2_req, 'sample_artifact', art2['id'])['small_blob'])

        # try to upload with smaller amount that doesn't exceeds quota
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 7)
            self.controller.upload_blob(
                user2_req, 'sample_artifact', art2['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, user2_req.context, 7, store_type='database')

        # check that blob was uploaded
        blob = self.controller.show(
            user2_req, 'sample_artifact', art2['id'])['small_blob']
        self.assertEqual(7, blob['size'])
        self.assertEqual('active', blob['status'])

        # create a sample artifacts for admin
        arta = self.controller.create(
            user2_req, 'sample_artifact', {'name': 'arta'})

        # Max small_blob size is 10. Admin has no quotas at all.
        # Since admin doesn't specify how many bytes he wants to upload,
        # engine can't verify it before upload. Therefore it allocates
        # 10 available bytes (max allowed small_blob size) for him and begins
        # upload. If uploaded data amount exceeds this limit
        # RequestEntityTooLarge is raised and upload fails.
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 11)
            self.assertRaises(
                exception.RequestEntityTooLarge,
                self.controller.upload_blob,
                admin_req, 'sample_artifact', arta['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, admin_req.context, 10, store_type='database')

        # check that blob wasn't uploaded
        self.assertIsNone(
            self.controller.show(
                admin_req, 'sample_artifact', arta['id'])['small_blob'])

        # try to upload with smaller amount that doesn't exceeds quota
        with mock.patch(
                'glare.common.store_api.save_blob_to_store',
                side_effect=store_api.save_blob_to_store) as mocked_save:
            data = BytesIO(b'a' * 10)
            self.controller.upload_blob(
                admin_req, 'sample_artifact', arta['id'], 'small_blob',
                data, 'application/octet-stream',
                content_length=None)
            mocked_save.assert_called_once_with(
                mock.ANY, data, admin_req.context, 10, store_type='database')

        # check that blob was uploaded
        blob = self.controller.show(
            admin_req, 'sample_artifact', arta['id'])['small_blob']
        self.assertEqual(10, blob['size'])
        self.assertEqual('active', blob['status'])
