# Copyright (c) 2016 Mirantis, Inc.
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


import json

from tempest import config
from tempest.lib.common import rest_client


CONF = config.CONF


class ArtifactsClient(rest_client.RestClient):

    def __init__(self, auth_provider):
        super(ArtifactsClient, self).__init__(
            auth_provider,
            CONF.artifacts.catalog_type,
            CONF.identity.region,
            endpoint_type=CONF.artifacts.endpoint_type)

    def create_artifact(self, type_name, name, version='0.0.0', **kwargs):
        kwargs.update({'name': name, 'version': version})
        uri = '/artifacts/{type_name}'.format(type_name=type_name)
        resp, body = self.post(uri, body=json.dumps(kwargs))
        self.expected_success(201, resp.status)
        parsed = self._parse_resp(body)
        return parsed

    def get_artifact(self, type_name, art_id):
        uri = '/artifacts/{type_name}/{id}'.format(
              type_name=type_name,
              id=art_id)
        resp, body = self.get(uri)
        self.expected_success(200, resp.status)
        parsed = self._parse_resp(body)
        return parsed

    def update_artifact(self, type_name, art_id, remove_props=None, **kwargs):
        headers = {'Content-Type': 'application/json-patch+json'}
        uri = '/artifacts/{type_name}/{id}'.format(type_name=type_name,
                                                   id=art_id)
        changes = []

        if remove_props:
            for prop_name in remove_props:
                if prop_name not in kwargs:
                    if '/' in prop_name:
                        changes.append({'op': 'remove',
                                        'path': '/%s' % prop_name})
                    else:
                        changes.append({'op': 'replace',
                                        'path': '/%s' % prop_name,
                                        'value': None})
        for prop_name in kwargs:
            changes.append({'op': 'add',
                            'path': '/%s' % prop_name,
                            'value': kwargs[prop_name]})
        resp, body = self.patch(uri, json.dumps(changes), headers=headers)
        self.expected_success(200, resp.status)
        parsed = self._parse_resp(body)
        return parsed

    def activate_artifact(self, type_name, art_id):
        return self.update_artifact(type_name, art_id, status='active')

    def deactivate_artifact(self, type_name, art_id):
        return self.update_artifact(type_name, art_id, status='deactivated')

    def reactivate_artifact(self, type_name, art_id):
        return self.update_artifact(type_name, art_id, status='active')

    def publish_artifact(self, type_name, art_id):
        return self.update_artifact(type_name, art_id, visibility='public')

    def upload_blob(self, type_name, art_id, blob_property, data):
        headers = {'Content-Type': 'application/octet-stream'}
        uri = '/artifacts/{type_name}/{id}/{blob_prop}'.format(
            type_name=type_name,
            id=art_id,
            blob_prop=blob_property)
        resp, body = self.put(uri, data, headers=headers)
        self.expected_success(200, resp.status)
        parsed = self._parse_resp(body)
        return parsed

    def download_blob(self, type_name, art_id, blob_property):
        uri = '/artifacts/{type_name}/{id}/{blob_prop}'.format(
            type_name=type_name,
            id=art_id,
            blob_prop=blob_property)
        resp, body = self.get(uri)
        self.expected_success(200, resp.status)
        parsed = self._parse_resp(body)
        return parsed

    def delete_artifact(self, type_name, art_id):
        uri = '/artifacts/{type_name}/{id}'.format(
            type_name=type_name,
            id=art_id)
        self.delete(uri)

    def list_artifacts(self, type_name):
        uri = '/artifacts/{}'.format(type_name)
        resp, body = self.get(uri)
        self.expected_success(200, resp.status)
        parsed = self._parse_resp(body)
        return parsed
