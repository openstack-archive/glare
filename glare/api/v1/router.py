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

from glare.api.v1 import resource
from glare.common import wsgi


class API(wsgi.Router):
    """WSGI router for Glare v1 API requests.

    API Router redirects incoming requests to appropriate WSGI resource method.
    """

    def __init__(self, mapper):

        glare_resource = resource.create_resource()
        reject_method_resource = wsgi.Resource(wsgi.RejectMethodController())

        # ---schemas---
        mapper.connect('/schemas',
                       controller=glare_resource,
                       action='list_type_schemas',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/schemas',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET')

        mapper.connect('/schemas/{type_name}',
                       controller=glare_resource,
                       action='show_type_schema',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/schemas/{type_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET')

        # ---artifacts---
        mapper.connect('/artifacts/{type_name}',
                       controller=glare_resource,
                       action='list',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}',
                       controller=glare_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/artifacts/{type_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST')

        mapper.connect('/artifacts/{type_name}/{artifact_id}',
                       controller=glare_resource,
                       action='update',
                       conditions={'method': ['PATCH']})
        mapper.connect('/artifacts/{type_name}/{artifact_id}',
                       controller=glare_resource,
                       action='show',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}/{artifact_id}',
                       controller=glare_resource,
                       action='delete',
                       conditions={'method': ['DELETE']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}/{artifact_id}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PATCH, DELETE')

        # ---tags---
        mapper.connect('/artifacts/{type_name}/{artifact_id}/tags',
                       controller=glare_resource,
                       action='set_tags',
                       conditions={'method': ['PUT']})
        mapper.connect('/artifacts/{type_name}/{artifact_id}/tags',
                       controller=glare_resource,
                       action='get_tags',
                       conditions={'method': ['GET']})
        mapper.connect('/artifacts/{type_name}/{artifact_id}/tags',
                       controller=glare_resource,
                       action='delete_tags',
                       conditions={'method': ['DELETE']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}/{artifact_id}/tags',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT, DELETE')

        # ---blobs---
        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}',
                       controller=glare_resource,
                       action='download_blob',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}',
                       controller=glare_resource,
                       action='upload_blob',
                       conditions={'method': ['PUT']})
        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT')

        # ---blob dicts---

        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}/'
                       '{blob_key}',
                       controller=glare_resource,
                       action='download_blob_dict',
                       conditions={'method': ['GET']},
                       body_reject=True)
        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}/'
                       '{blob_key}',
                       controller=glare_resource,
                       action='upload_blob_dict',
                       conditions={'method': ['PUT']})
        mapper.connect('/artifacts/{type_name}/{artifact_id}/{field_name}/'
                       '{blob_key}',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, PUT')

        super(API, self).__init__(mapper)
