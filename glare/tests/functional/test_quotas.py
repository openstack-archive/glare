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


class TestQuotasAPI(base.TestArtifact):
    """Test quotas REST API."""

    def setUp(self):
        base.functional.FunctionalTest.setUp(self)

        self.glare_server.deployment_flavor = 'noauth'

        self.glare_server.max_uploaded_data = '10000'
        self.glare_server.max_artifact_number = '150'

        self.glare_server.enabled_artifact_types = 'images,' \
                                                   'heat_templates,' \
                                                   'murano_packages,' \
                                                   'sample_artifact'
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')
        self.glare_server.artifact_type_section = """
[artifact_type:sample_artifact]
max_uploaded_data = 3000
[artifact_type:images]
max_uploaded_data = 15000
max_artifact_number = 30
[artifact_type:heat_templates]
max_artifact_number = 150
[artifact_type:murano_packages]
max_uploaded_data = 10000
max_artifact_number = 100
"""
        self.start_servers(**self.__dict__.copy())

    def test_quota_api_wrong(self):
        self.set_user('admin')

        url = '/quotas'
        # try to set wrong values
        values = [{"project1": "value1"}]
        self.put(url=url, data=values, status=400)

        # no quota name
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_value": 10
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # no quota value
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # no project id
        values = [
            {
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # no project quotas
        values = [
            {
                "project_id": "project1",
            }
        ]
        self.put(url=url, data=values, status=400)

        # quota name has more than 1 :
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "max:artifact:number",
                        "quota_value": 10
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # too long quota name
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "a" * 256,
                        "quota_value": 10
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # too long project name
        values = [
            {
                "project_id": "a" * 256,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # negative quota value less than -1
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": -2
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        # non-integer quota value
        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": "AAA"
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

        values = [
            {
                "project_id": "project1",
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10.5
                    }
                ]
            }
        ]
        self.put(url=url, data=values, status=400)

    @staticmethod
    def _deserialize_quotas(quotas):
        values = {}
        for item in quotas:
            project_id = item['project_id']
            values[project_id] = {}
            for quota in item['project_quotas']:
                values[project_id][quota['quota_name']] = quota['quota_value']
        return values

    def test_quota_api(self):
        self.set_user('admin')
        user1_tenant_id = self.users['user1']['tenant_id']
        user2_tenant_id = self.users['user2']['tenant_id']
        admin_tenant_id = self.users['admin']['tenant_id']
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number:images",
                        "quota_value": 3
                    },
                    {
                        "quota_name": "max_artifact_number:heat_templates",
                        "quota_value": 15
                    },
                    {
                        "quota_name": "max_artifact_number:murano_packages",
                        "quota_value": 10
                    },
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            },
            {
                "project_id": user2_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            },
            {
                "project_id": admin_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            }
        ]

        url = '/quotas'
        # define several quotas
        self.put(url=url, data=values)

        # get all quotas
        res = self.get(url=url)
        global_quotas = res['global_quotas']
        self.assertEqual({
            'max_artifact_number': 150,
            'max_artifact_number:heat_templates': 150,
            'max_artifact_number:images': 30,
            'max_artifact_number:murano_packages': 100,
            'max_uploaded_data': 10000,
            'max_uploaded_data:images': 15000,
            'max_uploaded_data:murano_packages': 10000,
            'max_uploaded_data:sample_artifact': 3000}, global_quotas)
        self.assertEqual(self._deserialize_quotas(values),
                         self._deserialize_quotas(res['quotas']))

        # get user1 quotas
        res = self._deserialize_quotas(self.get(
            url='/project-quotas/' + user1_tenant_id))
        self.assertEqual({user1_tenant_id: {
            'max_artifact_number': 10,
            'max_artifact_number:heat_templates': 15,
            'max_artifact_number:images': 3,
            'max_artifact_number:murano_packages': 10,
            'max_uploaded_data': 10000,
            'max_uploaded_data:images': 15000,
            'max_uploaded_data:murano_packages': 10000,
            'max_uploaded_data:sample_artifact': 3000}}, res)

        # get admin quotas
        res = self._deserialize_quotas(self.get(url='/project-quotas'))
        self.assertEqual({admin_tenant_id: {
            'max_artifact_number': 10,
            'max_artifact_number:heat_templates': 150,
            'max_artifact_number:images': 30,
            'max_artifact_number:murano_packages': 100,
            'max_uploaded_data': 10000,
            'max_uploaded_data:images': 15000,
            'max_uploaded_data:murano_packages': 10000,
            'max_uploaded_data:sample_artifact': 3000}}, res)

        # user1 can't set quotas
        self.set_user('user1')
        self.put(url=url, data=values, status=403)
        self.get(url=url, status=403)

        # user1 can get his quotas
        res = self._deserialize_quotas(self.get(url='/project-quotas'))
        self.assertEqual({user1_tenant_id: {
            'max_artifact_number': 10,
            'max_artifact_number:heat_templates': 15,
            'max_artifact_number:images': 3,
            'max_artifact_number:murano_packages': 10,
            'max_uploaded_data': 10000,
            'max_uploaded_data:images': 15000,
            'max_uploaded_data:murano_packages': 10000,
            'max_uploaded_data:sample_artifact': 3000}}, res)

        # user1 can't get user2 quotas
        self.get(url='/project-quotas/' + user2_tenant_id, status=403)


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
        self.assertEqual([], result['artifacts'])

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
        self.assertEqual([], result['artifacts'])

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


class TestDynamicQuotas(base.TestArtifact):
    """Test dynamic quota limits."""

    def setUp(self):
        base.functional.FunctionalTest.setUp(self)

        self.glare_server.deployment_flavor = 'noauth'

        self.glare_server.enabled_artifact_types = 'images,' \
                                                   'heat_templates,' \
                                                   'murano_packages,' \
                                                   'sample_artifact'
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')
        self.start_servers(**self.__dict__.copy())

    def test_count_artifact_number(self):
        self.set_user('admin')
        user1_tenant_id = self.users['user1']['tenant_id']
        admin_tenant_id = self.users['admin']['tenant_id']
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number:images",
                        "quota_value": 3
                    },
                    {
                        "quota_name": "max_artifact_number:heat_templates",
                        "quota_value": 15
                    },
                    {
                        "quota_name": "max_artifact_number:murano_packages",
                        "quota_value": 10
                    },
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            },
            {
                "project_id": admin_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": 10
                    }
                ]
            }
        ]
        url = '/quotas'
        # define several quotas
        self.put(url=url, data=values)

        self.set_user('user1')
        # initially there are no artifacts
        result = self.get('/all')
        self.assertEqual([], result['artifacts'])

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

        # disable global limit for user1 and try to create 15 heat templates
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number:images",
                        "quota_value": 3
                    },
                    {
                        "quota_name": "max_artifact_number:heat_templates",
                        "quota_value": 15
                    },
                    {
                        "quota_name": "max_artifact_number:murano_packages",
                        "quota_value": 10
                    },
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": -1
                    }
                ]
            }
        ]
        url = '/quotas'
        self.put(url=url, data=values)

        self.set_user("user1")
        for i in range(15):
            self.create_artifact(
                data={'name': 'ht%d' % i}, type_name='heat_templates')

        # creation of another heat template fails because of type limit
        self.create_artifact(
            data={'name': 'ht16'}, type_name='heat_templates', status=403)

        self.set_user("admin")
        # disable type limit for heat templates and create 1 heat templates
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_artifact_number:images",
                        "quota_value": 3
                    },
                    {
                        "quota_name": "max_artifact_number:heat_templates",
                        "quota_value": -1
                    },
                    {
                        "quota_name": "max_artifact_number:murano_packages",
                        "quota_value": 10
                    },
                    {
                        "quota_name": "max_artifact_number",
                        "quota_value": -1
                    }
                ]
            }
        ]
        url = '/quotas'
        self.put(url=url, data=values)

        # now user1 can create another heat template
        self.set_user("user1")
        self.create_artifact(
            data={'name': 'ht16'}, type_name='heat_templates')

    def test_calculate_uploaded_data(self):
        self.set_user('admin')
        user1_tenant_id = self.users['user1']['tenant_id']
        admin_tenant_id = self.users['admin']['tenant_id']
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_uploaded_data:images",
                        "quota_value": 1500
                    },
                    {
                        "quota_name": "max_uploaded_data:sample_artifact",
                        "quota_value": 300
                    },
                    {
                        "quota_name": "max_uploaded_data:murano_packages",
                        "quota_value": 1000
                    },
                    {
                        "quota_name": "max_uploaded_data",
                        "quota_value": 1000
                    }
                ]
            },
            {
                "project_id": admin_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_uploaded_data",
                        "quota_value": 1000
                    }
                ]
            }
        ]
        url = '/quotas'
        # define several quotas
        self.put(url=url, data=values)

        headers = {'Content-Type': 'application/octet-stream'}

        self.set_user('user1')
        # initially there are no artifacts
        result = self.get('/all')
        self.assertEqual([], result['artifacts'])

        # create 2 sample artifacts for user1
        art1 = self.create_artifact(data={'name': 'art1'})
        art2 = self.create_artifact(data={'name': 'art2'})

        # create 3 images for user1
        img1 = self.create_artifact(data={'name': 'img1'}, type_name='images')
        img2 = self.create_artifact(data={'name': 'img2'}, type_name='images')
        img3 = self.create_artifact(data={'name': 'img3'}, type_name='images')

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

        # disable global limit and try upload data from user1 again
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_uploaded_data:images",
                        "quota_value": 1500
                    },
                    {
                        "quota_name": "max_uploaded_data:sample_artifact",
                        "quota_value": 300
                    },
                    {
                        "quota_name": "max_uploaded_data:murano_packages",
                        "quota_value": 1000
                    },
                    {
                        "quota_name": "max_uploaded_data",
                        "quota_value": -1
                    }
                ]
            }
        ]
        url = '/quotas'
        self.put(url=url, data=values)

        self.set_user("user1")
        data = 'a' * 800
        self.put(url='/images/%s/image' % img2['id'],
                 data=data,
                 headers=headers)

        # uploading more fails because of image type limit
        data = 'a'
        self.put(url='/images/%s/image' % img3['id'],
                 data=data,
                 headers=headers,
                 status=413)

        # disable type limit and try upload data from user1 again
        self.set_user("admin")
        values = [
            {
                "project_id": user1_tenant_id,
                "project_quotas": [
                    {
                        "quota_name": "max_uploaded_data:images",
                        "quota_value": -1
                    },
                    {
                        "quota_name": "max_uploaded_data:sample_artifact",
                        "quota_value": 300
                    },
                    {
                        "quota_name": "max_uploaded_data:murano_packages",
                        "quota_value": 1000
                    },
                    {
                        "quota_name": "max_uploaded_data",
                        "quota_value": -1
                    }
                ]
            }
        ]
        url = '/quotas'
        self.put(url=url, data=values)

        self.set_user("user1")
        data = 'a' * 1000
        self.put(url='/images/%s/image' % img3['id'],
                 data=data,
                 headers=headers)
