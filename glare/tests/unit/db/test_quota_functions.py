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

from glare.db.sqlalchemy import api
from glare.tests.unit import base


class TestQuotaFunctions(base.BaseTestArtifactAPI):
    """Test quota db functions."""

    def setUp(self):
        super(TestQuotaFunctions, self).setUp()
        self.session = api.get_session()

    def test_count_artifact_number(self):
        # initially there are no artifacts
        self.assertEqual(0, api.count_artifact_number(
            self.req.context, self.session))

        # create 5 images, 3 heat templates, 2 murano packages and 7 samples
        amount = {
            'images': 5,
            'heat_templates': 3,
            'murano_packages': 2,
            'sample_artifact': 7
        }
        for type_name in amount:
            for num in range(amount[type_name]):
                self.controller.create(
                    self.req, type_name, {'name': type_name + str(num)})

        # create 1 artifact of each type from different user
        req = self.get_fake_request(self.users['user2'])
        for type_name in amount:
            self.controller.create(req, type_name, {'name': type_name})

        # count numbers for each type
        for type_name in amount:
            num = api.count_artifact_number(
                self.req.context, self.session, type_name)
            self.assertEqual(amount[type_name], num)

        # count the whole amount of artifacts
        self.assertEqual(17, api.count_artifact_number(
            self.req.context, self.session))

    def test_calculate_uploaded_data(self):
        # initially there is no data
        self.assertEqual(0, api.calculate_uploaded_data(
            self.req.context, self.session))

        # create a sample artifact
        art1 = self.controller.create(
            self.req, 'sample_artifact', {'name': 'art1'})

        # upload 10 bytes to 'blob'
        self.controller.upload_blob(
            self.req, 'sample_artifact', art1['id'], 'blob',
            BytesIO(b'a' * 10), 'application/octet-stream')
        self.assertEqual(10, api.calculate_uploaded_data(
            self.req.context, self.session))

        # upload 3 blobs to dict_of_blobs with 25, 35 and 45 bytes respectively
        self.controller.upload_blob(
            self.req, 'sample_artifact', art1['id'], 'dict_of_blobs/blob1',
            BytesIO(b'a' * 25), 'application/octet-stream')
        self.controller.upload_blob(
            self.req, 'sample_artifact', art1['id'], 'dict_of_blobs/blob2',
            BytesIO(b'a' * 35), 'application/octet-stream')
        self.controller.upload_blob(
            self.req, 'sample_artifact', art1['id'], 'dict_of_blobs/blob3',
            BytesIO(b'a' * 45), 'application/octet-stream')
        self.assertEqual(115, api.calculate_uploaded_data(
            self.req.context, self.session))

        # create another sample artifact and upload 100 bytes there
        art2 = self.controller.create(
            self.req, 'sample_artifact', {'name': 'art2'})
        self.controller.upload_blob(
            self.req, 'sample_artifact', art2['id'], 'blob',
            BytesIO(b'a' * 100), 'application/octet-stream')
        self.assertEqual(215, api.calculate_uploaded_data(
            self.req.context, self.session))

        # create image and upload 150 bytes there
        img1 = self.controller.create(
            self.req, 'images', {'name': 'img1'})
        self.controller.upload_blob(
            self.req, 'images', img1['id'], 'image',
            BytesIO(b'a' * 150), 'application/octet-stream')
        # the whole amount of uploaded data is 365 bytes
        self.assertEqual(365, api.calculate_uploaded_data(
            self.req.context, self.session))
        # 215 bytes for sample_artifact
        self.assertEqual(215, api.calculate_uploaded_data(
            self.req.context, self.session, 'sample_artifact'))
        # 150 bytes for images
        self.assertEqual(150, api.calculate_uploaded_data(
            self.req.context, self.session, 'images'))

        # create an artifact from another user and check that it's not included
        # for the original user
        req = self.get_fake_request(self.users['user2'])
        another_art = self.controller.create(
            req, 'sample_artifact', {'name': 'another'})
        # upload 1000 bytes to 'blob'
        self.controller.upload_blob(
            req, 'sample_artifact', another_art['id'], 'blob',
            BytesIO(b'a' * 1000), 'application/octet-stream')

        # original user still has 365 bytes
        self.assertEqual(365, api.calculate_uploaded_data(
            self.req.context, self.session))
        # user2 has 1000
        self.assertEqual(
            1000, api.calculate_uploaded_data(req.context, self.session))

    def test_quota_operations(self):
        # create several quotas
        values = {
            "project1": {
                "max_uploaded_data": 1000,
                "max_uploaded_data:images": 500,
                "max_artifact_number": 10
            },
            "project2": {
                "max_uploaded_data": 1000,
                "max_uploaded_data:sample_artifact": 500,
                "max_artifact_number": 20
            },
            "project3": {
                "max_uploaded_data": 1000
            }
        }

        api.set_quotas(values, self.session)

        res = api.get_all_quotas(self.session)
        self.assertEqual(values, res)

        # Redefine quotas
        new_values = {
            "project1": {
                "max_uploaded_data": 200,
                "max_uploaded_data:images": 1000,
                "max_artifact_number": 30,
                "max_artifact_number:images": 20
            },
            "project2": {},
        }

        api.set_quotas(new_values, self.session)

        # project3 should remain unchanged
        new_values['project3'] = {"max_uploaded_data": 1000}
        # project 2 quotas removed
        new_values.pop('project2')

        res = api.get_all_quotas(self.session)
        self.assertEqual(new_values, res)
