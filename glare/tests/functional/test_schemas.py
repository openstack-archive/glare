# Copyright 2016 OpenStack Foundation
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

import jsonschema

from oslo_serialization import jsonutils
import requests

from glare.tests import functional


class TestArtifact(functional.FunctionalTest):

    def setUp(self):
        super(TestArtifact, self).setUp()
        self.glare_server.deployment_flavor = 'noauth'
        self.glare_server.enabled_artifact_types = 'sample_artifact'
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.functional.sample_artifact')
        self.start_servers(**self.__dict__.copy())

    def tearDown(self):
        self.stop_servers()
        self._reset_database(self.glare_server.sql_connection)
        super(TestArtifact, self).tearDown()

    def _url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.glare_port, path)

    def _check_artifact_method(self, url, status=200):
        headers = {
            'X-Identity-Status': 'Confirmed',
        }
        response = requests.get(self._url(url), headers=headers)
        self.assertEqual(status, response.status_code, response.text)
        if status >= 400:
            return response.text
        if ("application/json" in response.headers["content-type"] or
                "application/schema+json" in response.headers["content-type"]):
            return jsonutils.loads(response.text)
        return response.text

    def get(self, url, status=200, headers=None):
        return self._check_artifact_method(url, status=status)

    def test_schemas(self):
        schema_sample_artifact = {
            u'sample_artifact': {
                u'name': u'sample_artifact',
                u'properties': {u'activated_at': {
                    u'description': u'Datetime when artifact has became '
                                    u'active.',
                    u'filter_ops': [u'eq',
                                    u'neq',
                                    u'in',
                                    u'gt',
                                    u'gte',
                                    u'lt',
                                    u'lte'],
                    u'format': u'date-time',
                    u'readOnly': True,
                    u'required_on_activate': False,
                    u'sortable': True,
                    u'type': [
                        u'string',
                        u'null']},
                    u'blob': {u'additionalProperties': False,
                              u'description': u'I am Blob',
                              u'filter_ops': [],
                              u'mutable': True,
                              u'properties': {u'checksum': {
                                  u'type': [u'string',
                                            u'null']},
                                  u'content_type': {
                                      u'type': u'string'},
                                  u'external': {
                                      u'type': u'boolean'},
                                  u'size': {u'type': [
                                      u'number',
                                      u'null']},
                                  u'status': {
                                      u'enum': [
                                          u'saving',
                                          u'active',
                                          u'pending_delete'],
                                      u'type': u'string'}},
                              u'required': [u'size',
                                            u'checksum',
                                            u'external',
                                            u'status',
                                            u'content_type'],
                              u'required_on_activate': False,
                              u'type': [u'object',
                                        u'null']},
                    u'bool1': {u'default': False,
                               u'filter_ops': [u'eq'],
                               u'required_on_activate': False,
                               u'type': [u'string',
                                         u'null']},
                    u'bool2': {u'default': False,
                               u'filter_ops': [u'eq'],
                               u'required_on_activate': False,
                               u'type': [u'string',
                                         u'null']},
                    u'created_at': {
                        u'description': u'Datetime when artifact has been '
                                        u'created.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in',
                                        u'gt',
                                        u'gte',
                                        u'lt',
                                        u'lte'],
                        u'format': u'date-time',
                        u'readOnly': True,
                        u'sortable': True,
                        u'type': u'string'},
                    u'dependency1': {u'filter_ops': [u'eq',
                                                     u'neq',
                                                     u'in'],
                                     u'required_on_activate': False,
                                     u'type': [u'string',
                                               u'null']},
                    u'dependency2': {u'filter_ops': [u'eq',
                                                     u'neq',
                                                     u'in'],
                                     u'required_on_activate': False,
                                     u'type': [u'string',
                                               u'null']},
                    u'description': {u'default': u'',
                                     u'description': u'Artifact description.',
                                     u'filter_ops': [u'eq',
                                                     u'neq',
                                                     u'in'],
                                     u'maxLength': 4096,
                                     u'mutable': True,
                                     u'required_on_activate': False,
                                     u'type': [u'string',
                                               u'null']},
                    u'dict_of_blobs': {
                        u'additionalProperties': {
                            u'additionalProperties': False,
                            u'properties': {u'checksum': {
                                u'type': [u'string',
                                          u'null']},
                                u'content_type': {
                                    u'type': u'string'},
                                u'external': {
                                    u'type': u'boolean'},
                                u'size': {
                                    u'type': [
                                        u'number',
                                        u'null']},
                                u'status': {
                                    u'enum': [
                                        u'saving',
                                        u'active',
                                        u'pending_delete'],
                                    u'type': u'string'}},
                            u'required': [u'size',
                                          u'checksum',
                                          u'external',
                                          u'status',
                                          u'content_type'],
                            u'type': [u'object',
                                      u'null']},
                        u'default': {},
                        u'filter_ops': [],
                        u'maxProperties': 255,
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'dict_of_int': {
                        u'additionalProperties': {
                            u'type': u'string'},
                        u'default': {},
                        u'filter_ops': [u'eq'],
                        u'maxProperties': 255,
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'dict_of_str': {
                        u'additionalProperties': {
                            u'type': u'string'},
                        u'default': {},
                        u'filter_ops': [u'eq'],
                        u'maxProperties': 255,
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'dict_validators': {
                        u'additionalProperties': False,
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxProperties': 3,
                        u'properties': {
                            u'abc': {u'type': [u'string',
                                               u'null']},
                            u'def': {u'type': [u'string',
                                               u'null']},
                            u'ghi': {u'type': [u'string',
                                               u'null']},
                            u'jkl': {u'type': [u'string',
                                               u'null']}},
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'float1': {u'filter_ops': [u'eq',
                                                u'neq',
                                                u'in',
                                                u'gt',
                                                u'gte',
                                                u'lt',
                                                u'lte'],
                                u'required_on_activate': False,
                                u'sortable': True,
                                u'type': [u'number',
                                          u'null']},
                    u'float2': {u'filter_ops': [u'eq',
                                                u'neq',
                                                u'in',
                                                u'gt',
                                                u'gte',
                                                u'lt',
                                                u'lte'],
                                u'required_on_activate': False,
                                u'sortable': True,
                                u'type': [u'number',
                                          u'null']},
                    u'icon': {u'additionalProperties': False,
                              u'description': u'Artifact icon.',
                              u'filter_ops': [],
                              u'properties': {u'checksum': {
                                  u'type': [u'string',
                                            u'null']},
                                  u'content_type': {
                                      u'type': u'string'},
                                  u'external': {
                                      u'type': u'boolean'},
                                  u'size': {
                                      u'type': [
                                          u'number',
                                          u'null']},
                                  u'status': {
                                      u'enum': [
                                          u'saving',
                                          u'active',
                                          u'pending_delete'],
                                      u'type': u'string'}},
                              u'required': [u'size',
                                            u'checksum',
                                            u'external',
                                            u'status',
                                            u'content_type'],
                              u'required_on_activate': False,
                              u'type': [u'object',
                                        u'null']},
                    u'id': {u'description': u'Artifact UUID.',
                            u'filter_ops': [u'eq',
                                            u'neq',
                                            u'in'],
                            u'maxLength': 255,
                            u'pattern': u'^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-'
                                        u'([0-9a-fA-F]){4}-([0-9a-fA-F]){4}-'
                                        u'([0-9a-fA-F]){12}$',
                            u'readOnly': True,
                            u'sortable': True,
                            u'type': u'string'},
                    u'int1': {u'filter_ops': [u'eq',
                                              u'neq',
                                              u'in',
                                              u'gt',
                                              u'gte',
                                              u'lt',
                                              u'lte'],
                              u'required_on_activate': False,
                              u'sortable': True,
                              u'type': [u'integer',
                                        u'null']},
                    u'int2': {u'filter_ops': [u'eq',
                                              u'neq',
                                              u'in',
                                              u'gt',
                                              u'gte',
                                              u'lt',
                                              u'lte'],
                              u'required_on_activate': False,
                              u'sortable': True,
                              u'type': [u'integer',
                                        u'null']},
                    u'int_validators': {u'filter_ops': [u'eq',
                                                        u'neq',
                                                        u'in',
                                                        u'gt',
                                                        u'gte',
                                                        u'lt',
                                                        u'lte'],
                                        u'maximum': 20,
                                        u'minumum': 10,
                                        u'required_on_activate': False,
                                        u'type': [u'integer',
                                                  u'null']},
                    u'license': {
                        u'description': u'Artifact license type.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxLength': 255,
                        u'required_on_activate': False,
                        u'type': [u'string',
                                  u'null']},
                    u'license_url': {
                        u'description': u'URL to artifact license.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxLength': 255,
                        u'required_on_activate': False,
                        u'type': [u'string',
                                  u'null']},
                    u'list_of_int': {u'default': [],
                                     u'filter_ops': [u'eq'],
                                     u'items': {
                                         u'type': u'string'},
                                     u'maxItems': 255,
                                     u'required_on_activate': False,
                                     u'type': [u'array',
                                               u'null']},
                    u'list_of_str': {u'default': [],
                                     u'filter_ops': [u'eq'],
                                     u'items': {
                                         u'type': u'string'},
                                     u'maxItems': 255,
                                     u'required_on_activate': False,
                                     u'type': [u'array',
                                               u'null']},
                    u'list_validators': {u'default': [],
                                         u'filter_ops': [
                                             u'eq',
                                             u'neq',
                                             u'in'],
                                         u'items': {
                                             u'type': u'string'},
                                         u'maxItems': 3,
                                         u'required_on_activate': False,
                                         u'type': [u'array',
                                                   u'null'],
                                         u'unique': True},
                    u'metadata': {u'additionalProperties': {
                        u'type': u'string'},
                        u'default': {},
                        u'description': u'Key-value dict with useful '
                                        u'information about an artifact.',
                        u'filter_ops': [u'eq',
                                        u'neq'],
                        u'maxProperties': 255,
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'name': {u'description': u'Artifact Name.',
                              u'filter_ops': [u'eq',
                                              u'neq',
                                              u'in'],
                              u'maxLength': 255,
                              u'required_on_activate': False,
                              u'sortable': True,
                              u'type': u'string'},
                    u'owner': {
                        u'description': u'ID of user/tenant who uploaded '
                                        u'artifact.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxLength': 255,
                        u'readOnly': True,
                        u'required_on_activate': False,
                        u'sortable': True,
                        u'type': u'string'},
                    u'provided_by': {
                        u'additionalProperties': False,
                        u'description': u'Info about artifact authors.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxProperties': 255,
                        u'properties': {
                            u'company': {u'type': u'string'},
                            u'href': {u'type': u'string'},
                            u'name': {u'type': u'string'}},
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'release': {
                        u'default': [],
                        u'description': u'Target Openstack release for '
                                        u'artifact. It is usually the same '
                                        u'when artifact was uploaded.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'items': {u'type': u'string'},
                        u'maxItems': 255,
                        u'required_on_activate': False,
                        u'type': [u'array',
                                  u'null'],
                        u'unique': True},
                    u'small_blob': {u'additionalProperties': False,
                                    u'filter_ops': [],
                                    u'mutable': True,
                                    u'properties': {u'checksum': {
                                        u'type': [u'string',
                                                  u'null']},
                                        u'content_type': {
                                            u'type': u'string'},
                                        u'external': {
                                            u'type': u'boolean'},
                                        u'size': {
                                            u'type': [
                                                u'number',
                                                u'null']},
                                        u'status': {
                                            u'enum': [
                                                u'saving',
                                                u'active',
                                                u'pending_delete'],
                                            u'type': u'string'}},
                                    u'required': [u'size',
                                                  u'checksum',
                                                  u'external',
                                                  u'status',
                                                  u'content_type'],
                                    u'required_on_activate': False,
                                    u'type': [u'object',
                                              u'null']},
                    u'status': {u'default': u'drafted',
                                u'description': u'Artifact status.',
                                u'enum': [u'drafted',
                                          u'active',
                                          u'deactivated',
                                          u'deleted'],
                                u'filter_ops': [u'eq',
                                                u'neq',
                                                u'in'],
                                u'sortable': True,
                                u'type': u'string'},
                    u'str1': {u'filter_ops': [u'eq',
                                              u'neq',
                                              u'in',
                                              u'gt',
                                              u'gte',
                                              u'lt',
                                              u'lte'],
                              u'maxLength': 255,
                              u'required_on_activate': False,
                              u'sortable': True,
                              u'type': [u'string',
                                        u'null']},
                    u'string_mutable': {u'filter_ops': [u'eq',
                                                        u'neq',
                                                        u'in',
                                                        u'gt',
                                                        u'gte',
                                                        u'lt',
                                                        u'lte'],
                                        u'maxLength': 255,
                                        u'mutable': True,
                                        u'required_on_activate': False,
                                        u'type': [u'string',
                                                  u'null']},
                    u'string_required': {
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in',
                                        u'gt',
                                        u'gte',
                                        u'lt',
                                        u'lte'],
                        u'maxLength': 255,
                        u'type': [u'string',
                                  u'null']},
                    u'string_validators': {
                        u'enum': [u'aa',
                                  u'bb',
                                  u'ccccccccccc',
                                  None],
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in',
                                        u'gt',
                                        u'gte',
                                        u'lt',
                                        u'lte'],
                        u'maxLength': 10,
                        u'required_on_activate': False,
                        u'type': [u'string',
                                  u'null']},
                    u'supported_by': {
                        u'additionalProperties': {
                            u'type': u'string'},
                        u'description': u'Info about persons who responsible '
                                        u'for artifact support',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in'],
                        u'maxProperties': 255,
                        u'required': [u'name'],
                        u'required_on_activate': False,
                        u'type': [u'object',
                                  u'null']},
                    u'system_attribute': {u'default': u'default',
                                          u'filter_ops': [u'eq',
                                                          u'neq',
                                                          u'in'],
                                          u'maxLength': 255,
                                          u'readOnly': True,
                                          u'sortable': True,
                                          u'type': [u'string',
                                                    u'null']},
                    u'tags': {u'default': [],
                              u'description': u'List of tags added to '
                                              u'Artifact.',
                              u'filter_ops': [u'eq',
                                              u'neq',
                                              u'in'],
                              u'items': {u'type': u'string'},
                              u'maxItems': 255,
                              u'mutable': True,
                              u'required_on_activate': False,
                              u'type': [u'array',
                                        u'null']},
                    u'updated_at': {
                        u'description': u'Datetime when artifact has been '
                                        u'updated last time.',
                        u'filter_ops': [u'eq',
                                        u'neq',
                                        u'in',
                                        u'gt',
                                        u'gte',
                                        u'lt',
                                        u'lte'],
                        u'format': u'date-time',
                        u'readOnly': True,
                        u'sortable': True,
                        u'type': u'string'},
                    u'version': {u'default': u'0.0.0',
                                 u'description': u'Artifact version(semver).',
                                 u'filter_ops': [u'eq',
                                                 u'neq',
                                                 u'in',
                                                 u'gt',
                                                 u'gte',
                                                 u'lt',
                                                 u'lte'],
                                 u'pattern': u'/^([0-9]+)\\.([0-9]+)\\.'
                                             u'([0-9]+)(?:-([0-9A-Za-z-]+'
                                             u'(?:\\.[0-9A-Za-z-]+)*))?'
                                             u'(?:\\+[0-9A-Za-z-]+)?$/',
                                 u'required_on_activate': False,
                                 u'sortable': True,
                                 u'type': u'string'},
                    u'visibility': {
                        u'default': u'private',
                        u'description': u'Artifact visibility that defines if '
                                        u'artifact can be available to other '
                                        u'users.',
                        u'filter_ops': [u'eq'],
                        u'maxLength': 255,
                        u'sortable': True,
                        u'type': u'string'}},
                u'required': [u'name'],
                u'title': u'Artifact type sample_artifact of version 1.0',
                u'type': u'object'}}

        # Get list schemas of artifacts
        result = self.get(url='/schemas')
        self.assertEqual({u'schemas': schema_sample_artifact}, result)

        # Get schema of sample_artifact
        result = self.get(url='/schemas/sample_artifact')
        self.assertEqual({u'schemas': schema_sample_artifact}, result)

        # Validation of schemas
        result = self.get(url='/schemas')['schemas']
        for artifact_type, schema in result.items():
            jsonschema.Draft4Validator.check_schema(schema)
