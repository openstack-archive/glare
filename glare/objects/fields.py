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

import uuid

import jsonschema
from jsonschema import exceptions as json_exceptions
from oslo_versionedobjects import fields
import semantic_version
import six
import six.moves.urllib.parse as urlparse

from glare.i18n import _


class ArtifactStatusField(fields.StateMachine):
    ARTIFACT_STATUS = (QUEUED, ACTIVE, DEACTIVATED, DELETED) = (
        'queued', 'active', 'deactivated', 'deleted')

    ALLOWED_TRANSITIONS = {
        QUEUED: {QUEUED, ACTIVE, DELETED},
        ACTIVE: {ACTIVE, DEACTIVATED, DELETED},
        DEACTIVATED: {DEACTIVATED, ACTIVE, DELETED},
        DELETED: {DELETED}
    }

    def __init__(self, **kwargs):
            super(ArtifactStatusField, self).__init__(self.ARTIFACT_STATUS,
                                                      **kwargs)


class Version(fields.FieldType):

    @staticmethod
    def coerce(obj, attr, value):
        return str(semantic_version.Version.coerce(str(value)))


class VersionField(fields.AutoTypedField):
    AUTO_TYPE = Version()


class BlobFieldType(fields.FieldType):
    """Blob field contains reference to blob location.
    """
    BLOB_STATUS = (SAVING, ACTIVE, PENDING_DELETE) = (
        'saving', 'active', 'pending_delete')

    BLOB_SCHEMA = {
        'type': 'object',
        'properties': {
            'url': {'type': ['string', 'null'], 'format': 'uri',
                    'max_length': 255},
            'size': {'type': ['number', 'null']},
            'checksum': {'type': ['string', 'null']},
            'external': {'type': 'boolean'},
            'id': {'type': 'string'},
            'status': {'type': 'string',
                       'enum': list(BLOB_STATUS)},
            'content_type': {'type': 'string'},
        },
        'required': ['url', 'size', 'checksum', 'external', 'status',
                     'id', 'content_type']
    }

    @staticmethod
    def coerce(obj, attr, value):
        """Validate and store blob info inside oslo.vo"""
        if not isinstance(value, dict):
            raise ValueError(_("Blob value must be dict. Got %s type instead")
                             % type(value))
        value.setdefault('id', str(uuid.uuid4()))
        try:
            jsonschema.validate(value, BlobFieldType.BLOB_SCHEMA)
        except json_exceptions.ValidationError as e:
            raise ValueError(e)

        return value

    @staticmethod
    def to_primitive(obj, attr, value):
        return {key: val for key, val in six.iteritems(value)
                if key not in ('url', 'id')}


class BlobField(fields.AutoTypedField):
    AUTO_TYPE = BlobFieldType()


class DependencyFieldType(fields.FieldType):
    """Dependency field specifies Artifact dependency on other artifact or some
    external resource. From technical perspective it is just soft link to Glare
    Artifact or https/http resource. So Artifact users can download the
    referenced file by that link.
    """

    @staticmethod
    def is_external(link):
        return link.startswith('http')

    @staticmethod
    def get_type_name(link):
        url = link.split('/')
        if len(url) == 4:
            return url[2]
        else:
            raise ValueError(_("It is not possible to "
                               "extract type_name from link %s"), link)

    @staticmethod
    def coerce(obj, attr, value):
        # to remove the existing dependency user sets its value to None,
        # we have to consider this case.
        if value is None:
            return value
        # check that value is string
        if not isinstance(value, six.string_types):
            raise ValueError(_('A string is required in field %(attr)s, '
                               'not a %(type)s') %
                             {'attr': attr, 'type': type(value).__name__})
        # determine if link is external or internal
        external = DependencyFieldType.is_external(value)
        # validate link itself
        if external:
            link = urlparse.urlparse(value)
            if link.scheme not in ('http', 'https'):
                raise ValueError(_('Only http and https requests '
                                   'are allowed in url %s') % value)
        else:
            result = value.split('/')
            if len(result) != 4 or result[1] != 'artifacts':
                raise ValueError(
                    _('Dependency link %(link)s is not valid in field '
                      '%(attr)s. The link must be either valid url or '
                      'reference to artifact. Example: '
                      '/artifacts/<artifact_type>/<artifact_id>'
                      ) % {'link': value, 'attr': attr})
        return value


class Dependency(fields.AutoTypedField):
    AUTO_TYPE = DependencyFieldType()


class List(fields.AutoTypedField):

    def __init__(self, element_type, **kwargs):
        self.AUTO_TYPE = fields.List(element_type())
        super(List, self).__init__(**kwargs)


class Dict(fields.AutoTypedField):

    def __init__(self, element_type, **kwargs):
        self.AUTO_TYPE = fields.Dict(element_type())
        super(Dict, self).__init__(**kwargs)
