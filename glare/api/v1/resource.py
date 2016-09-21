# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""WSGI Resource definition for Glare. Defines Glare API and serialization/
deserialization of incoming requests."""

import json
import jsonpatch
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
import six
from six.moves import http_client
import six.moves.urllib.parse as urlparse

from glare.api.v1 import api_versioning
from glare.common import exception as exc
from glare.common import wsgi
from glare import engine
from glare.i18n import _, _LI

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

list_configs = [
    cfg.IntOpt('default_api_limit', default=25,
               help=_('Default value for the number of items returned by a '
                      'request if not specified explicitly in the request')),
    cfg.IntOpt('max_api_limit', default=1000,
               help=_('Maximum permissible number of items that could be '
                      'returned by a request')),
]

CONF.register_opts(list_configs)

supported_versions = api_versioning.VersionedResource.supported_versions


class RequestDeserializer(api_versioning.VersionedResource,
                          wsgi.JSONRequestDeserializer):
    """Glare deserializer for incoming webop Requests.
    Deserializer converts incoming request into bunch of python primitives.
    So other components doesn't work with requests at all. Deserializer also
    executes primary API validation without any knowledge about Artifact
    structure.
    """

    @staticmethod
    def _get_content_type(req, expected=None):
        """Determine content type of the request body."""
        if "Content-Type" not in req.headers:
            msg = _("Content-Type must be specified.")
            LOG.error(msg)
            raise exc.BadRequest(msg)

        content_type = req.content_type
        if expected is not None and content_type not in expected:
            msg = (_('Invalid content type: %(ct)s. Expected: %(exp)s') %
                   {'ct': content_type, 'exp': ', '.join(expected)})
            raise exc.UnsupportedMediaType(message=msg)

        return content_type

    def _get_request_body(self, req):
        return self.from_json(req.body)

    @supported_versions(min_ver='1.0')
    def create(self, req):
        self._get_content_type(req, expected=['application/json'])
        body = self._get_request_body(req)
        if not isinstance(body, dict):
            msg = _("Dictionary expected as body value. Got %s.") % type(body)
            raise exc.BadRequest(msg)
        return {'values': body}

    @supported_versions(min_ver='1.0')
    def list(self, req):
        params = req.params.copy()
        marker = params.pop('marker', None)
        query_params = {}
        # step 1 - apply marker to query if exists
        if marker is not None:
            query_params['marker'] = marker

        # step 2 - apply limit (if exists OR setup default limit)
        limit = params.pop('limit', CONF.default_api_limit)
        try:
            limit = int(limit)
        except ValueError:
            msg = _("Limit param must be an integer.")
            raise exc.BadRequest(message=msg)
        if limit < 0:
            msg = _("Limit param must be positive.")
            raise exc.BadRequest(message=msg)
        query_params['limit'] = min(CONF.max_api_limit, limit)

        # step 3 - parse sort parameters
        if 'sort' in params:
            sort = []
            for sort_param in params.pop('sort').strip().split(','):
                key, _sep, direction = sort_param.partition(':')
                if direction and direction not in ('asc', 'desc'):
                    raise exc.BadRequest('Sort direction must be one of '
                                         '["asc", "desc"]. Got %s direction'
                                         % direction)
                sort.append((key, direction or 'desc'))
            query_params['sort'] = sort

        # step 4 - parse filter parameters
        filters = []
        for fname, fval in six.iteritems(params):
            if fname == 'version' and fval == 'latest':
                query_params['latest'] = True
            else:
                filters.append((fname, fval))

        query_params['filters'] = filters
        return query_params

    @supported_versions(min_ver='1.0')
    def update(self, req):
        self._get_content_type(
            req, expected=['application/json-patch+json'])
        body = self._get_request_body(req)
        patch = jsonpatch.JsonPatch(body)
        try:
            # Initially patch object doesn't validate input. It's only checked
            # we call get operation on each method
            tuple(map(patch._get_operation, patch.patch))
        except (jsonpatch.InvalidJsonPatch, TypeError):
            msg = _("Json Patch body is malformed")
            raise exc.BadRequest(msg)
        for patch_item in body:
            if patch_item['path'] == '/tags':
                msg = _("Cannot modify artifact tags with PATCH "
                        "request. Use special Tag API for that.")
                raise exc.BadRequest(msg)
        return {'patch': patch}

    def _deserialize_blob(self, req):
        content_type = self._get_content_type(req)
        if content_type == ('application/vnd+openstack.glare-custom-location'
                            '+json'):
            data = self._get_request_body(req)
            if 'url' not in data:
                msg = _("url is required when specifying external location. "
                        "Cannot find url in body: %s") % str(data)
                raise exc.BadRequest(msg)
        else:
            data = req.body_file
        return {'data': data, 'content_type': content_type}

    @supported_versions(min_ver='1.0')
    def upload_blob(self, req):
        return self._deserialize_blob(req)

    @supported_versions(min_ver='1.0')
    def upload_blob_dict(self, req):
        return self._deserialize_blob(req)

    @supported_versions(min_ver='1.0')
    def set_tags(self, req):
        self._get_content_type(req, expected=['application/json'])
        body = self._get_request_body(req)

        if 'tags' not in body:
            msg = _("Tag list must be in the body of request.")
            raise exc.BadRequest(msg)

        return {'tag_list': body['tags']}


def log_request_progress(f):
    def log_decorator(self, req, *args, **kwargs):
        LOG.debug("Request %(request_id)s for %(api_method)s successfully "
                  "deserialized. Pass request parameters to Engine",
                  {'request_id': req.context.request_id,
                   'api_method': f.__name__})
        result = f(self, req, *args, **kwargs)
        LOG.info(_LI(
            "Request %(request_id)s for artifact %(api_method)s "
            "successfully executed."), {'request_id': req.context.request_id,
                                        'api_method': f.__name__})
        return result
    return log_decorator


class ArtifactsController(api_versioning.VersionedResource):
    """API controller for Glare Artifacts.
    Artifact Controller prepares incoming data for Glare Engine and redirects
    data to appropriate engine method (so only controller is working with
    Engine. Once the data returned from Engine Controller returns data
    in appropriate format for Response Serializer.
    """

    def __init__(self):
        self.engine = engine.Engine()

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def list_type_schemas(self, req):
        type_schemas = self.engine.list_type_schemas(req.context)
        return type_schemas

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def show_type_schema(self, req, type_name):
        type_schema = self.engine.show_type_schema(req.context, type_name)
        return {type_name: type_schema}

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def create(self, req, type_name, values):
        """Create artifact record in Glare.

        :param req: User request
        :param type_name: Artifact type name
        :param values: dict with artifact fields {field_name: field_value}
        :return definition of created artifact
        """
        return self.engine.create(req.context, type_name, values)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def update(self, req, type_name, artifact_id, patch):
        """Update artifact record in Glare.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to update
        :param patch: json patch with artifact changes
        :return definition of updated artifact
        """
        return self.engine.update(req.context, type_name, artifact_id, patch)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def delete(self, req, type_name, artifact_id):
        """Delete artifact from Glare

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to delete
        """
        return self.engine.delete(req.context, type_name, artifact_id)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def show(self, req, type_name, artifact_id):
        """Show detailed artifact info

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to show
        :return: definition of requested artifact
        """
        return self.engine.get(req.context, type_name, artifact_id)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def list(self, req, type_name, filters, marker=None, limit=None,
             sort=None, latest=False):
        """List available artifacts

        :param req: User request
        :param type_name: Artifact type name
        :param filters: filters that need to be applied to artifact
        :param marker: the artifact that considered as begin of the list
        so all artifacts before marker (including marker itself) will not be
        added to artifact list
        :param limit: maximum number of items in list
        :param sort: sorting options
        :param latest: flag that indicates, that only artifacts with highest
        versions should be returned in output
        :return: list of artifacts
        """
        artifacts = self.engine.list(req.context, type_name, filters, marker,
                                     limit, sort, latest)
        result = {'artifacts': artifacts,
                  'type_name': type_name}
        if len(artifacts) != 0 and len(artifacts) == limit:
            result['next_marker'] = artifacts[-1]['id']
        return result

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def upload_blob(self, req, type_name, artifact_id, field_name, data,
                    content_type):
        """Upload blob into Glare repo

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of Artifact to reactivate
        :param field_name: name of blob field in artifact
        :param data: Artifact payload
        :param content_type: data content-type
        """
        if content_type == ('application/vnd+openstack.glare-custom-location'
                            '+json'):
            url = data.pop('url')
            return self.engine.add_blob_location(
                req.context, type_name, artifact_id, field_name, url, data)
        else:
            return self.engine.upload_blob(req.context, type_name, artifact_id,
                                           field_name, data, content_type)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def upload_blob_dict(self, req, type_name, artifact_id, field_name, data,
                         blob_key, content_type):
        """Upload blob into Glare repo

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of Artifact to reactivate
        :param field_name: name of blob field in artifact
        :param data: Artifact payload
        :param content_type: data content-type
        :param blob_key: blob key in dict
        """
        if content_type == ('application/vnd+openstack.glare-custom-location'
                            '+json'):
            url = data.pop('url')
            return self.engine.add_blob_dict_location(
                req.context, type_name, artifact_id,
                field_name, blob_key, url, data)
        else:
            return self.engine.upload_blob_dict(
                req.context, type_name, artifact_id,
                field_name, blob_key, data, content_type)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def download_blob(self, req, type_name, artifact_id, field_name):
        """Download blob data from Artifact

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of Artifact to reactivate
        :param field_name: name of blob field in artifact
        :return: iterator that returns blob data
        """
        data, meta = self.engine.download_blob(req.context, type_name,
                                               artifact_id, field_name)
        result = {'data': data, 'meta': meta}
        return result

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def download_blob_dict(self, req, type_name, artifact_id,
                           field_name, blob_key):
        """Download blob data from Artifact

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of Artifact to reactivate
        :param field_name: name of blob field in artifact
        :param blob_key: name of Dict of blobs (optional)
        :return: iterator that returns blob data
        """
        data, meta = self.engine.download_blob_dict(
            req.context, type_name, artifact_id, field_name, blob_key)
        result = {'data': data, 'meta': meta}
        return result

    @staticmethod
    def _tag_body_resp(af):
        return {'tags': af['tags']}

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def get_tags(self, req, type_name, artifact_id):
        return self._tag_body_resp(self.engine.get(
            req.context, type_name, artifact_id))

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def set_tags(self, req, type_name, artifact_id, tag_list):
        patch = [{'op': 'replace', 'path': '/tags', 'value': tag_list}]
        patch = jsonpatch.JsonPatch(patch)
        return self._tag_body_resp(self.engine.update(
            req.context, type_name, artifact_id, patch))

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def delete_tags(self, req, type_name, artifact_id):
        patch = [{'op': 'replace', 'path': '/tags', 'value': []}]
        patch = jsonpatch.JsonPatch(patch)
        self.engine.update(req.context, type_name, artifact_id, patch)


class ResponseSerializer(api_versioning.VersionedResource,
                         wsgi.JSONResponseSerializer):
    """Glare Response Serializer converts data received from Glare Engine
    (it consists from plain data types - dict, int, string, file descriptors,
    etc) to WSGI Requests. It also specifies proper response status and
    content type as specified by API design.
    """

    @staticmethod
    def _prepare_json_response(response, result,
                               content_type='application/json'):
        body = json.dumps(result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = content_type

    def list_type_schemas(self, response, type_schemas):
        self._prepare_json_response(response,
                                    {'schemas': type_schemas},
                                    content_type='application/schema+json')

    def show_type_schema(self, response, type_schema):
        self._prepare_json_response(response,
                                    {'schemas': type_schema},
                                    content_type='application/schema+json')

    @supported_versions(min_ver='1.0')
    def list_schemas(self, response, type_list):
        self._prepare_json_response(response, {'types': type_list})

    @supported_versions(min_ver='1.0')
    def create(self, response, artifact):
        self._prepare_json_response(response, artifact)
        response.status_int = http_client.CREATED

    @supported_versions(min_ver='1.0')
    def show(self, response, artifact):
        self._prepare_json_response(response, artifact)

    @supported_versions(min_ver='1.0')
    def update(self, response, artifact):
        self._prepare_json_response(response, artifact)

    @supported_versions(min_ver='1.0')
    def list(self, response, af_list):
        params = dict(response.request.params)
        params.pop('marker', None)

        encode_params = {}
        for key, value in six.iteritems(params):
            encode_params[key] = encodeutils.safe_encode(value)
        query = urlparse.urlencode(encode_params)

        type_name = af_list['type_name']
        body = {
            type_name: af_list['artifacts'],
            'first': '/artifacts/%s' % type_name,
            'schema': '/schemas/%s' % type_name,
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in af_list:
            params['marker'] = af_list['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = '/artifacts/%s?%s' % (type_name, next_query)
        response.unicode_body = six.text_type(json.dumps(body,
                                                         ensure_ascii=False))
        response.content_type = 'application/json'

    @supported_versions(min_ver='1.0')
    def delete(self, response, result):
        response.status_int = http_client.NO_CONTENT

    @supported_versions(min_ver='1.0')
    def upload_blob(self, response, artifact):
        self._prepare_json_response(response, artifact)

    @staticmethod
    def _serialize_blob(response, result):
        data, meta = result['data'], result['meta']
        response.headers['Content-Type'] = meta['content_type']
        response.headers['Content-MD5'] = meta['md5']
        response.headers['X-Openstack-Glare-Content-SHA1'] = meta['sha1']
        response.headers['X-Openstack-Glare-Content-SHA256'] = meta['sha256']
        response.headers['Content-Length'] = str(meta['size'])
        response.app_iter = iter(data)

    @staticmethod
    def _serialize_location(response, result):
        data, meta = result['data'], result['meta']
        response.headers['Content-MD5'] = meta['md5']
        response.headers['X-Openstack-Glare-Content-SHA1'] = meta['sha1']
        response.headers['X-Openstack-Glare-Content-SHA256'] = meta['sha256']
        response.location = data['url']
        response.content_type = 'application/json'
        response.status = http_client.MOVED_PERMANENTLY
        response.content_length = 0

    @supported_versions(min_ver='1.0')
    def download_blob(self, response, result):
        external = result['meta']['external']
        if external:
            self._serialize_location(response, result)
        else:
            self._serialize_blob(response, result)

    @supported_versions(min_ver='1.0')
    def download_blob_dict(self, response, result):
        external = result['meta']['external']
        if external:
            self._serialize_location(response, result)
        else:
            self._serialize_blob(response, result)

    @supported_versions(min_ver='1.0')
    def delete_tags(self, response, result):
        response.status_int = http_client.NO_CONTENT


def create_resource():
    """Artifact resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ArtifactsController()
    return wsgi.Resource(controller, deserializer, serializer)
