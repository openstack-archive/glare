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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_versionedobjects import base
from oslo_versionedobjects import fields

from glare.common import exception
from glare.common import utils
from glare.db import artifact_api
from glare.i18n import _
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators
from glare.objects.meta import wrappers

global_artifact_opts = [
    cfg.IntOpt('max_uploaded_data', default=-1,  # disabled
               min=-1,
               help=_("Defines how many bytes of data user can upload to "
                      "storage. This parameter is global and doesn't take "
                      "into account data of what type was uploaded. "
                      "Value -1 means no limit.")),
    cfg.IntOpt('max_artifact_number', default=-1,  # disabled
               min=-1,
               help=_("Defines how many artifacts user can have. This "
                      "parameter is global and doesn't take "
                      "into account artifacts of what type were created. "
                      "Value -1 means no limit.")),
    cfg.BoolOpt('delayed_delete', default=False,
                help=_("If False defines that artifacts must be deleted "
                       "immediately after the user call. Otherwise they just "
                       "will be marked as deleted so they can be scrubbed "
                       "by some other tool in the background.")),
]

CONF = cfg.CONF
CONF.register_opts(global_artifact_opts)

LOG = logging.getLogger(__name__)


class BaseArtifact(base.VersionedObject):
    """BaseArtifact is a central place in Glare. It execute Glare business
    logic operations and checks in like:
    1) Check if artifact satisfies all requirements and can be activated
    2) Check that artifact is not deactivated and download blobs
    ...
    BaseArtifact interacts with database and saves/request artifact info
    from specified database API. Base Artifact is an abstract class so
    all concrete classes must be inherited from that class. Concrete classes
    must define custom fields in addition to BaseArtifact fields and db_api
    that must be used for interaction with database.
    """

    OBJ_PROJECT_NAMESPACE = 'glare'

    DEFAULT_ARTIFACT_VERSION = '0.0.0'

    STATUS = ('drafted', 'active', 'deactivated', 'deleted')

    DEFAULT_QUERY_COMBINER = "and"

    Field = wrappers.Field.init
    DictField = wrappers.DictField.init
    ListField = wrappers.ListField.init
    Blob = wrappers.BlobField.init

    fields = {
        'id': Field(fields.StringField, system=True,
                    validators=[validators.UUID()], nullable=False,
                    sortable=True, description="Artifact UUID."),
        'name': Field(fields.StringField, required_on_activate=False,
                      nullable=False, sortable=True,
                      validators=[validators.MinStrLen(1)],
                      description="Artifact Name.",
                      filter_ops=(wrappers.FILTER_LIKE, wrappers.FILTER_EQ,
                                  wrappers.FILTER_NEQ, wrappers.FILTER_IN)),
        'owner': Field(fields.StringField, system=True,
                       required_on_activate=False, nullable=False,
                       sortable=True, description="ID of user/tenant who "
                                                  "uploaded artifact."),
        'status': Field(fields.StringField, default='drafted',
                        nullable=False, sortable=True, mutable=True,
                        validators=[validators.AllowedValues(STATUS)],
                        description="Artifact status."),
        'created_at': Field(fields.DateTimeField, system=True,
                            nullable=False, sortable=True,
                            description="Datetime when artifact has "
                                        "been created."),
        'updated_at': Field(fields.DateTimeField, system=True,
                            nullable=False, sortable=True, mutable=True,
                            description="Datetime when artifact has "
                                        "been updated last time."),
        'activated_at': Field(fields.DateTimeField, system=True,
                              required_on_activate=False, sortable=True,
                              description="Datetime when artifact has became "
                                          "active."),
        'description': Field(fields.StringField, mutable=True,
                             required_on_activate=False, default="",
                             validators=[validators.MaxStrLen(4096)],
                             filter_ops=[],
                             description="Artifact description."),
        'tags': ListField(fields.String, mutable=True,
                          required_on_activate=False,
                          # tags are filtered without any operators
                          filter_ops=[],
                          validators=[validators.Unique(convert_to_set=True)],
                          element_validators=[
                              validators.ForbiddenChars([',', '/']),
                              validators.MinStrLen(1)
                          ],
                          description="List of tags added to Artifact."),
        'metadata': DictField(fields.String, required_on_activate=False,
                              element_validators=[validators.MinStrLen(1)],
                              description="Key-value dict with useful "
                                          "information about an artifact."),
        'visibility': Field(fields.StringField, default='private',
                            nullable=False, sortable=True, mutable=True,
                            validators=[validators.AllowedValues(
                                ['private', 'public'])],
                            description="Artifact visibility that defines "
                                        "if artifact can be available to "
                                        "other users."),
        'version': Field(glare_fields.VersionField, required_on_activate=False,
                         default=DEFAULT_ARTIFACT_VERSION, nullable=False,
                         sortable=True, validators=[validators.Version()],
                         description="Artifact version(semver)."),
        'display_type_name': Field(fields.StringField, system=True,
                                   description="Display name of "
                                               "artifact type.",
                                   sortable=True,
                                   filter_ops=(wrappers.FILTER_LIKE,
                                               wrappers.FILTER_EQ,
                                               wrappers.FILTER_NEQ,
                                               wrappers.FILTER_IN))
    }

    common_artifact_type_opts = [
        cfg.IntOpt('max_uploaded_data', min=-1, default=-1,
                   help=_("Defines how many bytes of data of this type user "
                          "can upload to storage. Value -1 means no limit.")),
        cfg.IntOpt('max_artifact_number', min=-1, default=-1,
                   help=_("Defines how many artifacts of this type user can "
                          "have. Value -1 means no limit.")),
        cfg.BoolOpt('delayed_delete',
                    help=_(
                        "If False defines that artifacts must be deleted "
                        "immediately after the user call. Otherwise they just "
                        "will be marked as deleted so they can be scrubbed "
                        "by some other tool in the background. "
                        "Redefines global parameter of the same name "
                        "from [DEFAULT] section.")),
        cfg.StrOpt('default_store',
                   choices=('file', 'filesystem', 'http', 'https', 'swift',
                            'swift+http', 'swift+https', 'swift+config', 'rbd',
                            'sheepdog', 'cinder', 'vsphere', 'database'),
                   help=_("""
The default scheme to use for storing artifacts of this
type.
Provide a string value representing the default scheme to
use for storing artifact data. If not set, Glare uses
default_store parameter from [glance_store] section.
NOTE: The value given for this configuration option must
be a valid scheme for a store registered with the ``stores``
configuration option.
Possible values:
   * file
   * filesystem
   * http
   * https
   * swift
   * swift+http
   * swift+https
   * swift+config
   * rbd
   * sheepdog
   * cinder
   * vsphere
   * database
"""))
    ]

    artifact_type_opts = []

    @classmethod
    def list_artifact_type_opts(cls):
        return cls.artifact_type_opts + cls.common_artifact_type_opts

    db_api = artifact_api.ArtifactAPI()

    @classmethod
    def is_blob(cls, field_name):
        """Helper to check that a field is a blob.

        :param field_name: name of the field
        :return: True if the field is a blob, False otherwise
        """
        return isinstance(cls.fields.get(field_name), glare_fields.BlobField)

    @classmethod
    def is_blob_dict(cls, field_name):
        """Helper to check that field is a blob dict.

        :param field_name: name of the field
        :return: True if the field is a blob dict, False otherwise
        """
        return (isinstance(cls.fields.get(field_name), glare_fields.Dict) and
                cls.fields[field_name].element_type ==
                glare_fields.BlobFieldType)

    @classmethod
    def init_artifact(cls, context, values):
        """Initialize an empty versioned object with values.

        Initialize vo object with default values and values specified by user.
        Also reset all changes of initialized object so user can track own
        changes.

        :param context: user context
        :param values: values needs to be set
        :return: artifact with initialized values
        """
        af = cls(context)
        # setup default values for all non specified fields
        default_fields = []
        for field in af.fields:
            if field not in values:
                default_fields.append(field)
        if default_fields:
            af.obj_set_defaults(*default_fields)

        # apply values specified by user
        for name, value in values.items():
            setattr(af, name, value)
        return af

    @classmethod
    def get_type_name(cls):
        """Return type name that allows to find artifact type in Glare

        Type name allows to find artifact type definition in Glare registry.

        :return: string that identifies current artifact type
        """
        raise NotImplementedError()

    @classmethod
    def get_display_type_name(cls):
        """
        Provides verbose Artifact type name which any external user can
        understand easily.

        :return: general purpose name for Artifact
        """
        return None

    def create(self, context):
        """Create new artifact in Glare repo.

        :param context: user context
        :return: created artifact object
        """
        values = self.obj_changes_to_primitive()
        values['type_name'] = self.get_type_name()
        values['display_type_name'] = self.get_display_type_name()

        LOG.debug("Sending request to create artifact of type '%(type_name)s'."
                  " New values are %(values)s",
                  {'type_name': self.get_type_name(), 'values': values})

        af_vals = self.db_api.save(context, None, values)
        return self.init_artifact(context, af_vals)

    def save(self, context):
        """Save artifact in Glare repo.

        :param context: user context
        :return: updated artifact object
        """
        values = self.obj_changes_to_primitive()

        LOG.debug("Sending request to update artifact '%(af_id)s'. "
                  "New values are %(values)s",
                  {'af_id': self.id, 'values': values})

        updated_af = self.db_api.save(context, self.id, values)
        return self.init_artifact(context, updated_af)

    @classmethod
    def show(cls, context, artifact_id, get_any_artifact=False):
        """Return Artifact from Glare repo

        :param context: user context
        :param artifact_id: id of requested artifact
        :return: requested artifact object
        """
        if cls.get_type_name() != 'all':
            type_name = cls.get_type_name()
        else:
            type_name = None
        af = cls.db_api.get(context, type_name, artifact_id, get_any_artifact)
        return cls.init_artifact(context, af)

    @classmethod
    def _get_field_type(cls, obj):
        """Get string representation of field type for filters."""
        if isinstance(obj, fields.IntegerField) or obj is fields.Integer:
            return 'int'
        elif isinstance(obj, fields.FloatField) or obj is fields.Float:
            return 'numeric'
        elif isinstance(obj, fields.FlexibleBooleanField) or \
                obj is fields.FlexibleBoolean:
            return 'bool'
        return 'string'

    @classmethod
    def _parse_sort_values(cls, sort):
        """Prepare sorting parameters for database."""
        new_sort = []
        for key, direction in sort:
            if key not in cls.fields:
                msg = _("The field %s doesn't exist.") % key
                raise exception.BadRequest(msg)
            # check if field can be sorted
            if not cls.fields[key].sortable:
                msg = _("The field %s is not sortable.") % key
                raise exception.BadRequest(msg)
            new_sort.append((key, direction, cls._get_field_type(
                cls.fields.get(key))))
        return new_sort

    @classmethod
    def _validate_filter_ops(cls, filter_name, op):
        field = cls.fields.get(filter_name)
        if op not in field.filter_ops:
            msg = (_("Unsupported filter type '%(key)s'."
                     "The following filters are supported "
                     "%(filters)s") % {
                'key': op, 'filters': str(field.filter_ops)})
            raise exception.BadRequest(message=msg)

    @classmethod
    def _parse_filter_values(cls, filters):
        # input format for filters is list of tuples:
        # (filter_name, filter_value)
        # output format for filters is list of tuples:
        # (field_name, key_name, op, field_type, value)
        new_filters = []

        for filter_name, filter_value in filters:
            if filter_name in ('tags-any', 'tags'):
                tag_values = filter_value
                combiner = cls.DEFAULT_QUERY_COMBINER
                if filter_value.startswith(("and:", "or:")):
                    combiner = filter_value[:filter_value.index(":")]
                    tag_values = filter_value[filter_value.index(":") + 1:]
                if ':' in tag_values:
                    msg = _("Tags are filtered without operator")
                    raise exception.BadRequest(msg)
                new_filters.append(
                    (filter_name, None, None, None, tag_values,
                     combiner))
                continue

            key_name = None
            if '.' in filter_name:
                filter_name, key_name = filter_name.rsplit('.', 1)
                if not isinstance(cls.fields.get(filter_name),
                                  glare_fields.Dict):
                    msg = _("Field %s is not Dict") % filter_name
                    raise exception.BadRequest(msg)

            if cls.fields.get(filter_name) is None:
                msg = _("Unable filter '%s'") % filter_name
                raise exception.BadRequest(msg)

            field_type = cls.fields.get(filter_name)
            if isinstance(field_type, glare_fields.List) or isinstance(
                    field_type, glare_fields.Dict) and key_name is not None:
                field_type = field_type.element_type

            try:
                query_combiner, op, val = utils.split_filter_op(filter_value)

                if isinstance(field_type, glare_fields.Dict):
                    if op not in ['eq', 'in']:
                        msg = (_("Unsupported filter type '%s'. The following "
                                 "filters are supported: eq, in") % op)
                        raise exception.BadRequest(message=msg)
                    if query_combiner not in ["and", "or"]:
                        msg = (_("Unsupported Query combiner type '%s'. Only "
                                 "following combiner are allowed: and, or")
                               % query_combiner)
                        raise exception.BadRequest(message=msg)
                    if op == 'in':
                        new_filters.append((
                            filter_name, utils.split_filter_value_for_quotes(
                                val), op, None, None, query_combiner))
                    else:
                        new_filters.append((
                            filter_name, val, op, None, None, query_combiner))
                else:
                    cls._validate_filter_ops(filter_name, op)
                    if op == 'in':
                        value = [field_type.coerce(cls(), filter_name, value)
                                 for value in
                                 utils.split_filter_value_for_quotes(val)]
                    else:
                        value = field_type.coerce(cls(), filter_name, val)
                    new_filters.append(
                        (filter_name, key_name, op,
                         cls._get_field_type(field_type),
                         value, query_combiner))
            except ValueError:
                msg = _("Invalid filter value: %s") % str(val)
                raise exception.BadRequest(msg)

        return new_filters

    @classmethod
    def list(cls, context, filters=None, marker=None, limit=None,
             sort=None, latest=False, list_all_artifacts=False):
        """Return list of artifacts requested by user.

        :param context: user context
        :param filters: filters that need to be applied to artifact
        :param marker: the artifact that considered as begin of the list
        so all artifacts before marker (including marker itself) will not be
        added to artifact list
        :param limit: maximum number of items in the list
        :param sort: sorting options
        :param latest: flag that indicates, that only artifacts with highest
        versions should be returned in output
        :param list_all_artifacts: flag that indicate, if the list should
        return artifact from all tenants (True),
        or from the specific tenant (False)
        :return: list of artifact objects
        """

        default_sort_parameters = (
            ('created_at', 'desc', None), ('id', 'asc', None))
        # Parse sort parameters and update them with defaults
        sort = [] if sort is None else cls._parse_sort_values(sort)
        for default_sort in default_sort_parameters:
            for s in sort:
                # If the default sort parameter already in the list - skip it
                if s[0] == default_sort[0]:
                    break
            else:
                sort.append(default_sort)

        default_filter_parameters = [
            ('status', None, 'neq', None, 'deleted',
             cls.DEFAULT_QUERY_COMBINER)]
        if cls.get_type_name() != 'all':
            default_filter_parameters.append(
                ('type_name', None, 'eq', None, cls.get_type_name(),
                 cls.DEFAULT_QUERY_COMBINER))
        # Parse filter parameters and update them with defaults
        filters = [] if filters is None else cls._parse_filter_values(filters)
        for default_filter in default_filter_parameters:
            if default_filter not in filters:
                filters.append(default_filter)

        artifacts_data = cls.db_api.list(context, filters, marker, limit,
                                         sort, latest, list_all_artifacts)
        artifacts_data["artifacts"] = [cls.init_artifact(context, af)
                                       for af in artifacts_data["artifacts"]]
        return artifacts_data

    @classmethod
    def delete(cls, context, af):
        """Delete artifact and all its blobs from Glare.

        :param context: user context
        :param af: artifact object targeted for deletion
        """
        # marking artifact as deleted
        cls.db_api.save(context, af.id, {'status': 'deleted'})

        # collect all uploaded blobs
        blobs = {}
        for name in af.fields:
            if cls.is_blob(name) or cls.is_blob_dict(name):
                field = getattr(af, name)
                if field:
                    blobs[name] = field

        LOG.debug("Marked artifact %(artifact)s as deleted.",
                  {'artifact': af.id})

        return blobs

    @classmethod
    def get_max_blob_size(cls, field_name):
        """Get the maximum allowed blob size in bytes.

        :param field_name: blob or blob dict field name
        :return: maximum blob size in bytes
        """
        return getattr(cls.fields[field_name], 'max_blob_size')

    @classmethod
    def get_max_folder_size(cls, field_name):
        """Get the maximum allowed folder size in bytes.

        :param field_name: folder (blob dict) field name
        :return: maximum folder size in bytes
        """
        return getattr(cls.fields[field_name], 'max_folder_size')

    @classmethod
    def update_blob(cls, context, af_id, field_name, values):
        """Update blob info in database.

        :param context: user context
        :param af_id: id of modified artifact
        :param field_name: blob or blob dict field name
        :param values: updated blob values
        :return: updated artifact definition in Glare
        """
        af_upd = cls.db_api.update_blob(context, af_id, {field_name: values})
        return cls.init_artifact(context, af_upd)

    # Next comes a collection of hooks for various operations

    @classmethod
    def pre_create_hook(cls, context, af):
        pass

    @classmethod
    def post_create_hook(cls, context, af):
        pass

    @classmethod
    def pre_update_hook(cls, context, af):
        pass

    @classmethod
    def pre_update_hook_with_patch(cls, context, af, json_patch):
        cls.pre_update_hook(context, af)

    @classmethod
    def post_update_hook(cls, context, af):
        pass

    @classmethod
    def pre_activate_hook(cls, context, af):
        pass

    @classmethod
    def post_activate_hook(cls, context, af):
        pass

    @classmethod
    def pre_publish_hook(cls, context, af):
        pass

    @classmethod
    def post_publish_hook(cls, context, af):
        pass

    @classmethod
    def pre_deactivate_hook(cls, context, af):
        pass

    @classmethod
    def post_deactivate_hook(cls, context, af):
        pass

    @classmethod
    def pre_reactivate_hook(cls, context, af):
        pass

    @classmethod
    def post_reactivate_hook(cls, context, af):
        pass

    @classmethod
    def pre_upload_hook(cls, context, af, field_name, blob_key, fd):
        return fd

    @classmethod
    def post_upload_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def pre_add_location_hook(
            cls, context, af, field_name, blob_key, location):
        pass

    @classmethod
    def post_add_location_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def pre_download_hook(cls, context, af, field_name, blob_key):
        pass

    @classmethod
    def post_download_hook(cls, context, af, field_name, blob_key, fd):
        return fd

    @classmethod
    def pre_delete_hook(cls, context, af):
        pass

    @classmethod
    def post_delete_hook(cls, context, af):
        pass

    @classmethod
    def format_all(cls, values):
        """Specify output format for 'all' artifact meta-type

        :param values: dict with values that need to be formatted
        """
        return values

    def to_notification(self):
        """Return notification body that can be send to listeners.

        :return: dict with notification information
        """
        return {
            'type': self.get_type_name(),
            'id': self.id,
            'description': self.description,
            'name': self.name,
            'version': self.version,
            'visibility': self.visibility,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'activated_at': self.activated_at,
            'owner': self.owner
        }

    def to_dict(self):
        """Convert oslo versioned object to dictionary.

        :return: dict with field names and field values
        """
        return self.obj_to_primitive()['versioned_object.data']

    def obj_changes_to_primitive(self):
        changes = self.obj_get_changes()
        res = {}
        for key, val in changes.items():
            if val is not None and hasattr(val, 'to_primitive'):
                res[key] = val.to_primitive()
            else:
                res[key] = val
        return res

    @classmethod
    def _schema_field(cls, field, field_name=''):
        field_type = utils.get_schema_type(field)
        schema = {}

        # generate schema for validators
        for val in getattr(field, 'validators', []):
            schema.update(val.to_jsonschema())

        schema['type'] = (field_type
                          if not field.nullable else [field_type, 'null'])
        schema['glareType'] = utils.get_glare_type(field)
        output_blob_schema = {
            'type': ['object', 'null'],
            'properties': {
                'size': {'type': ['number', 'null']},
                'md5': {'type': ['string', 'null']},
                'sha1': {'type': ['string', 'null']},
                'sha256': {'type': ['string', 'null']},
                'external': {'type': 'boolean'},
                'status': {'type': 'string',
                           'enum': list(
                               glare_fields.BlobFieldType.BLOB_STATUS)},
                'content_type': {'type': 'string'},
            },
            'required': ['size', 'md5', 'sha1', 'sha256', 'external', 'status',
                         'content_type'],
            'additionalProperties': False
        }

        if field.system:
            schema['readOnly'] = True

        if isinstance(field, glare_fields.Dict):
            element_type = utils.get_schema_type(field.element_type)
            property_validators = schema.pop('propertyValidators', [])
            if field.element_type is glare_fields.BlobFieldType:
                schema['additionalProperties'] = output_blob_schema
            else:
                if schema.get('properties'):
                    properties = {}
                    required = schema.pop('required', [])
                    for key in schema.pop('properties'):
                        properties[key] = {
                            'type': (element_type
                                     if key in required
                                     else [element_type, 'null'])}
                        for val in property_validators:
                            properties[key].update(val)
                    schema['properties'] = properties
                    schema['additionalProperties'] = False
                else:
                    schema['additionalProperties'] = {'type': element_type}
                    for val in property_validators:
                        schema['additionalProperties'].update(val)

        if isinstance(field, glare_fields.List):
            items_validators = schema.pop('itemValidators', [])
            schema['items'] = {
                'type': utils.get_schema_type(field.element_type)}
            for val in items_validators:
                schema['items'].update(val)

        if isinstance(field, glare_fields.BlobField):
            schema.update(output_blob_schema)

        if isinstance(field, fields.DateTimeField):
            schema['format'] = 'date-time'

        if field_name == 'status':
            schema['enum'] = cls.STATUS

        if field.description:
            schema['description'] = field.description
        if field.mutable:
            schema['mutable'] = True
        if field.sortable:
            schema['sortable'] = True
        if not field.required_on_activate:
            schema['required_on_activate'] = False
        if field._default is not None:
            schema['default'] = field._default
        if field.metadata is not None:
            schema['metadata'] = field.metadata

        schema['filter_ops'] = field.filter_ops

        return schema

    @classmethod
    def gen_schemas(cls):
        """Return json schema representation of the artifact type."""
        schemas_prop = {}
        for field_name, field in cls.fields.items():
            schemas_prop[field_name] = cls._schema_field(
                field, field_name=field_name)
        schemas = {'properties': schemas_prop,
                   'name': cls.get_type_name(),
                   'version': cls.VERSION,
                   'title': 'Artifact type %s of version %s' %
                            (cls.get_type_name(), cls.VERSION),
                   'type': 'object',
                   'display_name': cls.get_display_type_name(),
                   'required': ['name']}

        return schemas
