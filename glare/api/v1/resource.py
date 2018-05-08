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
import jsonschema
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
from glare.i18n import _

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

QUOTA_SCHEMA = {
    'type': 'object',
    'properties': {
        'quota_name': {
            u'maxLength': 255,
            u'minLength': 1,
            u'pattern': u'^[^:]*:?[^:]*$',  # can have only 1 or 0 ':'
            u'type': u'string'},
        'quota_value': {'type': 'integer', u'minimum': -1},
    },
    'required': ['quota_name', 'quota_value']
}

QUOTA_INPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "items": {
        "properties": {
            "project_id": {
                u'maxLength': 255,
                u'minLength': 1,
                "type": "string"
            },
            "project_quotas": {
                "items": QUOTA_SCHEMA,
                "type": "array"
            }
        },
        "type": "object",
        "required": ["project_id", "project_quotas"]
    },
    "type": "array"
}


class RequestDeserializer(api_versioning.VersionedResource,
                          wsgi.JSONRequestDeserializer):
    """Glare deserializer for incoming webob requests.

    Deserializer checks and converts incoming request into a bunch of Glare
    primitives. So other service components don't work with requests at all.
    Deserializer also performs primary API validation without any knowledge
    about concrete artifact type structure.
    """

    ALLOWED_LOCATION_TYPES = ('external', 'internal')

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

    @staticmethod
    def _get_content_length(req):
        """Determine content length of the request body."""
        if req.content_length is None:
            return

        try:
            content_length = int(req.content_length)
            if content_length < 0:
                raise ValueError
        except ValueError:
            msg = _("Content-Length must be a non negative integer.")
            LOG.error(msg)
            raise exc.BadRequest(msg)

        return content_length

    def _get_request_body(self, req):
        """Get request json body and convert it to python structures."""
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
        for fname, fval in params.items():
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
            # when we call get operation on each method
            tuple(map(patch._get_operation, patch.patch))
        except (jsonpatch.InvalidJsonPatch, TypeError, AttributeError,
                jsonpatch.JsonPointerException):
            msg = _("Json Patch body is malformed")
            raise exc.BadRequest(msg)
        return {'patch': patch}

    @supported_versions(min_ver='1.0')
    def upload_blob(self, req):
        content_type = self._get_content_type(req)
        content_length = self._get_content_length(req)
        if content_type == ('application/vnd+openstack.glare-custom-location'
                            '+json'):
            data = self._get_request_body(req)
            if 'url' not in data:
                msg = _("url is required when specifying external location. "
                        "Cannot find 'url' in request body: %s") % str(data)
                raise exc.BadRequest(msg)
            location_type = data.get('location_type', 'external')
            if location_type not in self.ALLOWED_LOCATION_TYPES:
                msg = (_("Incorrect location type '%(location_type)s'. It "
                         "must be one of the following %(allowed)s") %
                       {'location_type': location_type,
                        'allowed': ', '.join(self.ALLOWED_LOCATION_TYPES)})
                raise exc.BadRequest(msg)
            if location_type == 'external':
                url = data.get('url')
                if not url.startswith('http'):
                    msg = _("Url '%s' doesn't have http(s) scheme") % url
                    raise exc.BadRequest(msg)
                if 'md5' not in data:
                    msg = _("Incorrect blob metadata. MD5 must be specified "
                            "for external location in artifact blob.")
                    raise exc.BadRequest(msg)
        else:
            data = req.body_file

        if self.is_valid_encoding(req) and self.is_valid_method(req):
            req.is_body_readable = True

        return {'data': data,
                'content_type': content_type,
                'content_length': content_length}

    @supported_versions(min_ver='1.1')
    def set_quotas(self, req):
        self._get_content_type(req, expected=['application/json'])
        body = self._get_request_body(req)
        try:
            jsonschema.validate(body, QUOTA_INPUT_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise exc.BadRequest(e)
        values = {}
        for item in body:
            project_id = item['project_id']
            values[project_id] = {}
            for quota in item['project_quotas']:
                values[project_id][quota['quota_name']] = quota['quota_value']
        return {'values': values}

    # TODO(mfedosin) add pagination to list of quotas


def log_request_progress(f):
    def log_decorator(self, req, *args, **kwargs):
        LOG.debug("Request %(request_id)s for %(api_method)s successfully "
                  "deserialized. Pass request parameters to Engine",
                  {'request_id': req.context.request_id,
                   'api_method': f.__name__})
        result = f(self, req, *args, **kwargs)
        LOG.info(
            "Request %(request_id)s for artifact %(api_method)s "
            "successfully executed.", {'request_id': req.context.request_id,
                                       'api_method': f.__name__})
        return result
    return log_decorator


class ArtifactsController(api_versioning.VersionedResource):
    """API controller for Glare Artifacts.

    Artifact Controller prepares incoming data for Glare Engine and redirects
    data to the appropriate engine method. Once the response data is returned
    from the engine Controller passes it next to Response Serializer.
    """

    def __init__(self):
        self.engine = engine.Engine()

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def list_type_schemas(self, req):
        """List of detailed descriptions of enabled artifact types.

        :param req: user request
        :return: list of json-schemas of all enabled artifact types.
        """
        return self.engine.show_type_schemas(req.context)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def show_type_schema(self, req, type_name):
        """Get detailed artifact type description.

        :param req: user request
        :param type_name: artifact type name
        :return: json-schema representation of artifact type
        """
        type_schema = self.engine.show_type_schemas(req.context, type_name)
        return {type_name: type_schema}

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def create(self, req, type_name, values):
        """Create artifact record in Glare.

        :param req: user request
        :param type_name: artifact type name
        :param values: dict with artifact fields
        :return: definition of created artifact
        """
        if req.context.project_id is None or req.context.read_only:
            msg = _("It's forbidden to anonymous users to create artifacts.")
            raise exc.Forbidden(msg)
        if not values.get('name'):
            msg = _("Name must be specified at creation.")
            raise exc.BadRequest(msg)
        for field in ('visibility', 'status', 'display_type_name'):
            if field in values:
                msg = _("%s is not allowed in a request at creation.") % field
                raise exc.BadRequest(msg)
        return self.engine.create(req.context, type_name, values)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def update(self, req, type_name, artifact_id, patch):
        """Update artifact record in Glare.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to update
        :param patch: json patch with artifact changes
        :return: definition of updated artifact
        """
        return self.engine.save(req.context, type_name, artifact_id, patch)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def delete(self, req, type_name, artifact_id):
        """Delete artifact from Glare.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to delete
        """
        return self.engine.delete(req.context, type_name, artifact_id)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def show(self, req, type_name, artifact_id):
        """Show detailed artifact info.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to show
        :return: definition of requested artifact
        """
        return self.engine.show(req.context, type_name, artifact_id)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def list(self, req, type_name, filters=None, marker=None, limit=None,
             sort=None, latest=False):
        """List available artifacts.

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
        :return: list of requested artifact definitions
        """
        artifacts_data = self.engine.list(req.context, type_name, filters,
                                          marker, limit, sort, latest)
        artifacts = artifacts_data["artifacts"]
        result = {'artifacts': artifacts,
                  'type_name': type_name,
                  'total_count': artifacts_data['total_count']}
        if len(artifacts) != 0 and len(artifacts) == limit:
            result['next_marker'] = artifacts[-1]['id']
        return result

    @staticmethod
    def _parse_blob_path(blob_path):
        field_name, _sep, blob_key = blob_path.partition('/')
        if not blob_key:
            blob_key = None
        return field_name, blob_key

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def upload_blob(self, req, type_name, artifact_id, blob_path, data,
                    content_type, content_length=None):
        """Upload blob into Glare repo.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact where to perform upload
        :param blob_path: path to artifact blob
        :param data: blob payload
        :param content_type: data content-type
        :param content_length: amount of data user wants to upload
        :return: definition of requested artifact with uploaded blob
        """
        field_name, blob_key = self._parse_blob_path(blob_path)
        if content_type == ('application/vnd+openstack.glare-custom-location'
                            '+json'):
            url = data.pop('url')
            return self.engine.add_blob_location(
                req.context, type_name, artifact_id, field_name, url, data,
                blob_key)
        else:
            return self.engine.upload_blob(
                req.context, type_name, artifact_id, field_name, data,
                content_type, content_length, blob_key)

    @supported_versions(min_ver='1.0')
    @log_request_progress
    def download_blob(self, req, type_name, artifact_id, blob_path):
        """Download blob data from Artifact.

        :param req: User request
        :param type_name: artifact type name
        :param artifact_id: id of artifact from where to perform download
        :param blob_path: path to artifact blob
        :return: requested blob data
        """
        field_name, blob_key = self._parse_blob_path(blob_path)
        data, meta = self.engine.download_blob(
            req.context, type_name, artifact_id, field_name, blob_key)
        result = {'data': data, 'meta': meta}
        return result

    @supported_versions(min_ver='1.1')
    @log_request_progress
    def delete_external_blob(self, req, type_name, artifact_id, blob_path):
        """Delete blob with external location from Glare repo.

        :param req: User request
        :param type_name: Artifact type name
        :param artifact_id: id of artifact with the blob to delete
        :param blob_path: path to artifact blob
        """
        field_name, blob_key = self._parse_blob_path(blob_path)
        return self.engine.delete_external_blob(
            req.context, type_name, artifact_id, field_name, blob_key)

    @supported_versions(min_ver='1.1')
    @log_request_progress
    def set_quotas(self, req, values):
        """Set quota records in Glare.

        :param req: user request
        :param values: list with quota values to set
        """
        self.engine.set_quotas(req.context, values)

    @supported_versions(min_ver='1.1')
    @log_request_progress
    def list_all_quotas(self, req):
        """Get detailed info about all available quotas.

        :param req: user request
        :return: definition of requested quotas for the project
        """
        return self.engine.list_all_quotas(req.context)

    @supported_versions(min_ver='1.1')
    @log_request_progress
    def list_project_quotas(self, req, project_id=None):
        """Get detailed info about project quotas.

        :param req: user request
        :param project_id: id of the project for which to show quotas
        :return: definition of requested quotas for the project
        """
        return self.engine.list_project_quotas(req.context, project_id)


class ResponseSerializer(api_versioning.VersionedResource,
                         wsgi.JSONResponseSerializer):
    """Glare serializer for outgoing responses.

    Converts data received from the engine to WSGI responses. It also
    specifies proper response status and content type as declared in the API.
    """

    @staticmethod
    def _prepare_json_response(response, result,
                               content_type='application/json'):
        body = json.dumps(result, ensure_ascii=False)
        response.text = six.text_type(body)
        response.content_type = content_type + '; charset=UTF-8'

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
        for key, value in params.items():
            encode_params[key] = encodeutils.safe_encode(value)
        query = urlparse.urlencode(encode_params)

        type_name = af_list['type_name']
        body = {
            'type_name': type_name,
            'artifacts': af_list['artifacts'],
            'first': '/artifacts/%s' % type_name,
            'schema': '/schemas/%s' % type_name,
            'total_count': af_list['total_count']
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in af_list:
            params['marker'] = af_list['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = '/artifacts/%s?%s' % (type_name, next_query)

        self._prepare_json_response(response, body)

    @supported_versions(min_ver='1.0')
    def delete(self, response, result):
        response.status_int = http_client.NO_CONTENT

    @supported_versions(min_ver='1.0')
    def upload_blob(self, response, artifact):
        self._prepare_json_response(response, artifact)

    @staticmethod
    def _serialize_blob(response, result):
        data, meta = result['data'], result['meta']
        response.app_iter = iter(data)
        response.headers['Content-Type'] = meta['content_type']
        response.headers['Content-MD5'] = meta['md5']
        response.headers['X-Openstack-Glare-Content-SHA1'] = meta['sha1']
        response.headers['X-Openstack-Glare-Content-SHA256'] = meta['sha256']
        response.content_length = str(meta['size'])

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

    @supported_versions(min_ver='1.1')
    def delete_external_blob(self, response, result):
        self._prepare_json_response(response, result)

    @staticmethod
    def _serialize_quota(quotas):
        res = []
        for project_id, project_quotas in quotas.items():
            quota_list = []
            for quota_name, quota_value in project_quotas.items():
                quota_list.append({
                    'quota_name': quota_name,
                    'quota_value': quota_value,
                })
            res.append({
                'project_id': project_id,
                'project_quotas': quota_list
            })
        return res

    @supported_versions(min_ver='1.1')
    def list_all_quotas(self, response, quotas):
        quotas['quotas'] = self._serialize_quota(quotas['quotas'])
        self._prepare_json_response(response, quotas)

    @supported_versions(min_ver='1.1')
    def list_project_quotas(self, response, quotas):
        quotas = self._serialize_quota(quotas)
        self._prepare_json_response(response, quotas)


def create_resource():
    """Artifact resource factory method."""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ArtifactsController()
    return wsgi.Resource(controller, deserializer, serializer)
