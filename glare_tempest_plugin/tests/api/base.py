# Copyright 2016 Red Hat, Inc.
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


from glare_tempest_plugin import clients
from tempest.common import credentials_factory as common_creds
from tempest import config
from tempest.lib import base
from tempest.lib.common import dynamic_creds


CONF = config.CONF


class BaseArtifactTest(base.BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super(BaseArtifactTest, cls).setUpClass()
        cls.resource_setup()
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    @classmethod
    def get_client_with_isolated_creds(cls, type_of_creds="admin"):
        creds = cls.get_configured_isolated_creds(
            type_of_creds=type_of_creds)

        os = clients.Manager(credentials=creds)
        client = os.artifact_client
        return client

    @classmethod
    def resource_setup(cls):
        if not CONF.service_available.glare:
            skip_msg = "Glare is disabled"
            raise cls.skipException(skip_msg)
        if not hasattr(cls, "os"):
            creds = cls.get_configured_isolated_creds(
                type_of_creds='primary')
            cls.os_primary = clients.Manager(credentials=creds)
        cls.artifacts_client = cls.os_primary.artifacts_client

    @classmethod
    def get_configured_isolated_creds(cls, type_of_creds='admin'):
        identity_version = CONF.identity.auth_version
        if identity_version == 'v3':
            cls.admin_role = CONF.identity.admin_role
            cls.identity_uri = CONF.identity.uri_v3
        else:
            cls.admin_role = 'admin'
            cls.identity_uri = CONF.identity.uri
        cls.dynamic_cred = dynamic_creds.DynamicCredentialProvider(
            identity_version=CONF.identity.auth_version,
            identity_uri=cls.identity_uri,
            name=cls.__name__, admin_role=cls.admin_role,
            admin_creds=common_creds.get_configured_admin_credentials(
                'identity_admin'))
        if type_of_creds == 'primary':
            creds = cls.dynamic_cred.get_primary_creds()
        elif type_of_creds == 'admin':
            creds = cls.dynamic_cred.get_admin_creds()
        elif type_of_creds == 'alt':
            creds = cls.dynamic_cred.get_alt_creds()
        else:
            creds = cls.dynamic_cred.get_credentials(type_of_creds)
        cls.dynamic_cred.type_of_creds = type_of_creds

        return creds.credentials
