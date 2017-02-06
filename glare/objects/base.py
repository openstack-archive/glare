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

from copy import deepcopy
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils
from oslo_versionedobjects import base
from oslo_versionedobjects import fields
import six
import six.moves.urllib.request as urlrequest

from glare.common import exception
from glare.common import store_api
from glare.common import utils
from glare.db import artifact_api
from glare import locking
from glare.i18n import _, _LI
from glare.objects.meta import attribute
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import validators

artifact_opts = [
    cfg.BoolOpt('delayed_blob_delete', default=False,
                help=_("Defines if blob must be deleted immediately "
                       "or just marked as pending delete so it can be cleaned "
                       "by some other tool in the background.")),
]

CONF = cfg.CONF
CONF.register_opts(artifact_opts)

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

    STATUS = glare_fields.ArtifactStatusField

    Field = attribute.Attribute.init
    DictField = attribute.DictAttribute.init
    ListField = attribute.ListAttribute.init
    Blob = attribute.BlobAttribute.init

    fields = {
        'id': Field(fields.StringField, system=True,
                    validators=[validators.UUID()], nullable=False,
                    sortable=True, description="Artifact UUID."),
        'name': Field(fields.StringField, required_on_activate=False,
                      nullable=False, sortable=True,
                      description="Artifact Name."),
        'owner': Field(fields.StringField, system=True,
                       required_on_activate=False, nullable=False,
                       sortable=True, description="ID of user/tenant who "
                                                  "uploaded artifact."),
        'status': Field(glare_fields.ArtifactStatusField,
                        default=glare_fields.ArtifactStatusField.DRAFTED,
                        nullable=False, sortable=True,
                        description="Artifact status."),
        'created_at': Field(fields.DateTimeField, system=True,
                            filter_ops=attribute.FILTERS,
                            nullable=False, sortable=True,
                            description="Datetime when artifact has "
                                        "been created."),
        'updated_at': Field(fields.DateTimeField, system=True,
                            filter_ops=attribute.FILTERS,
                            nullable=False, sortable=True,
                            description="Datetime when artifact has "
                                        "been updated last time."),
        'activated_at': Field(fields.DateTimeField, system=True,
                              filter_ops=attribute.FILTERS,
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
                          element_validators=[validators.ForbiddenChars(
                              [',', '/'])],
                          description="List of tags added to Artifact."),
        'metadata': DictField(fields.String, required_on_activate=False,
                              element_validators=[validators.MinStrLen(1)],
                              filter_ops=(attribute.FILTER_EQ,
                                          attribute.FILTER_NEQ),
                              description="Key-value dict with useful "
                                          "information about an artifact."),
        'visibility': Field(fields.StringField, default='private',
                            nullable=False, filter_ops=(attribute.FILTER_EQ,),
                            sortable=True,
                            description="Artifact visibility that defines "
                                        "if artifact can be available to "
                                        "other users."),
        'version': Field(glare_fields.VersionField, required_on_activate=False,
                         default=DEFAULT_ARTIFACT_VERSION,
                         filter_ops=attribute.FILTERS, nullable=False,
                         sortable=True, validators=[validators.Version()],
                         description="Artifact version(semver).")
    }

    db_api = artifact_api.ArtifactAPI()
    lock_engine = locking.LockEngine(artifact_api.ArtifactLockApi())

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
    def is_link(cls, field_name):
        """Helper to check that a field is a link.

        :param field_name: name of the field
        :return: True if field is a link, False otherwise
        """
        return isinstance(cls.fields.get(field_name), glare_fields.Link)

    @classmethod
    def is_link_dict(cls, field_name):
        """Helper to check that a field is a link dict.

        :param field_name: name of the field
        :return: True if field is a link dict, False otherwise
        """
        return (isinstance(cls.fields.get(field_name), glare_fields.Dict) and
                cls.fields[field_name].element_type ==
                glare_fields.LinkFieldType)

    @classmethod
    def is_link_list(cls, field_name):
        """Helper to check that a field is a link list.

        :param field_name: name of the field
        :return: True if the field is a link list, False otherwise
        """
        return (isinstance(cls.fields.get(field_name), glare_fields.List) and
                cls.fields[field_name].element_type ==
                glare_fields.LinkFieldType)

    @classmethod
    def _init_artifact(cls, context, values):
        """Initialize an empty versioned object with values.

        Initialize vo object with default values and values specified by user.
        Also reset all changes of initialized object so user can track own
        changes.

        :param context: user context
        :param values: values needs to be set
        :return: artifact with initialized values
        """
        af = cls(context)
        # setup default values for all non specified attributes
        default_attrs = []
        for attr in af.fields:
            if attr not in values:
                default_attrs.append(attr)
        if default_attrs:
            af.obj_set_defaults(*default_attrs)

        # apply values specified by user
        for name, value in six.iteritems(values):
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
    def _get_scoped_lock(cls, af, values):
        """Create scope lock for artifact update.

        :param values: artifact values
        :return: Lock object
        """
        name = values.get('name', af.name)
        version = values.get('version', af.version)
        visibility = values.get('visibility', af.visibility)
        scope_id = None
        if (name, version, visibility) != (af.name, af.version, af.visibility):
            # no version change == no lock for version
            scope_id = "%s:%s:%s" % (cls.get_type_name(), name, str(version))
            if visibility != 'public':
                scope_id += ':%s' % str(af.obj_context.tenant)

        return cls.lock_engine.acquire(af.obj_context, scope_id)

    @classmethod
    def create(cls, context, values):
        """Create new artifact in Glare repo.

        :param context: user context
        :param values: dictionary with specified artifact fields
        :return: created artifact object
        """
        name = values.get('name')
        ver = values.setdefault(
            'version', cls.DEFAULT_ARTIFACT_VERSION)
        scope_id = "%s:%s:%s" % (cls.get_type_name(), name, ver)
        with cls.lock_engine.acquire(context, scope_id):
            cls._validate_versioning(context, name, ver)
            # validate other values
            cls._validate_change_allowed(values)
            # validate visibility
            if 'visibility' in values:
                msg = _("visibility is not allowed in a request "
                        "for artifact create.")
                raise exception.BadRequest(msg)
            values['id'] = str(uuid.uuid4())
            values['owner'] = context.tenant
            values['created_at'] = timeutils.utcnow()
            values['updated_at'] = values['created_at']
            af = cls._init_artifact(context, values)
            LOG.info(_LI("Parameters validation for artifact creation "
                         "passed for request %s."), context.request_id)
            af_vals = cls.db_api.create(
                context, af._obj_changes_to_primitive(), cls.get_type_name())
            return cls._init_artifact(context, af_vals)

    @classmethod
    def _validate_versioning(cls, context, name, version, is_public=False):
        """Validate if artifact with given name and version already exists.

        :param context: user context
        :param name: name of artifact to be checked
        :param version: version of artifact
        :param is_public: flag that indicates to search artifact globally
        """
        if version is not None and name not in (None, ""):
            filters = [('name', name), ('version', version)]
            if is_public is False:
                filters.extend([('owner', context.tenant),
                                ('visibility', 'private')])
            else:
                filters.extend([('visibility', 'public')])
            if len(cls.list(context, filters)) > 0:
                msg = _("Artifact with this name and version is already "
                        "exists for this owner.")
                raise exception.Conflict(msg)
        else:
            msg = _("Cannot set artifact version without name and version.")
            raise exception.BadRequest(msg)

    @classmethod
    def _validate_change_allowed(cls, field_names, af=None,
                                 validate_blob_names=True):
        """Validate if fields can be updated in artifact."""
        af_status = cls.STATUS.DRAFTED if af is None else af.status
        if af_status not in (cls.STATUS.ACTIVE, cls.STATUS.DRAFTED):
            msg = _("Forbidden to change attributes "
                    "if artifact not active or drafted.")
            raise exception.Forbidden(message=msg)

        for field_name in field_names:
            if field_name not in cls.fields:
                msg = _("%s field does not exist") % field_name
                raise exception.BadRequest(msg)
            field = cls.fields[field_name]
            if field.system is True:
                msg = _("Cannot specify system field %s. It is not "
                        "available for modifying by users.") % field_name
                raise exception.Forbidden(msg)
            if af_status == cls.STATUS.ACTIVE and not field.mutable:
                msg = (_("Forbidden to change field '%s' after activation.")
                       % field_name)
                raise exception.Forbidden(message=msg)
            if validate_blob_names and \
                    (cls.is_blob(field_name) or cls.is_blob_dict(field_name)):
                msg = _("Cannot add blob %s with this request. "
                        "Use special Blob API for that.") % field_name
                raise exception.BadRequest(msg)

    @classmethod
    def update(cls, context, af, values):
        """Update artifact in Glare repo.

        :param context: user context
        :param af: current definition of artifact
        :param values: dictionary with changes for artifact
        :return: updated artifact object
        """
        # reset all changes of artifact to reuse them after update
        af.obj_reset_changes()
        with cls._get_scoped_lock(af, values):
            # validate version
            if 'name' in values or 'version' in values:
                new_name = values.get('name') or af.name
                new_version = values.get('version') or af.version
                cls._validate_versioning(context, new_name, new_version)

            # validate other values
            cls._validate_change_allowed(values, af)
            # apply values to the artifact. if all changes applied then update
            # values in db or raise an exception in other case.
            for key, value in six.iteritems(values):
                try:
                    # check updates for links and validate them
                    if cls.is_link(key) and value is not None:
                        cls._validate_link(key, value, context)
                    elif cls.is_link_dict(key) and value:
                        for l in value:
                            cls._validate_link(key, value[l], context)
                    elif cls.is_link_list(key) and value:
                        for l in value:
                            cls._validate_link(key, l, context)
                except Exception as e:
                    msg = (_("Bad link in artifact %(af)s: %(msg)s")
                           % {"af": af.id, "msg": str(e)})
                    raise exception.BadRequest(msg)
                setattr(af, key, value)

            LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                         "update passed for request %(request)s."),
                     {'artifact': af.id, 'request': context.request_id})
            updated_af = cls.db_api.update(
                context, af.id, af._obj_changes_to_primitive())
            return cls._init_artifact(context, updated_af)

    @classmethod
    def get_action_for_updates(cls, context, af, values):
        """Define the appropriate method for artifact update.

        Based on update params this method defines what action engine should
        call for artifact update: activate, deactivate, reactivate, publish or
        just a regular update of artifact fields.

        :param context: user context
        :param af: current definition of artifact
        :param values: dictionary with changes for artifact
        :return: method reference for updates dict
        """
        action = cls.update
        if 'visibility' in values:
            # validate publish action format
            action = cls.publish
        elif 'status' in values:
            status = values['status']
            if status == cls.STATUS.DEACTIVATED:
                action = cls.deactivate
            elif status == cls.STATUS.ACTIVE:
                if af.status == af.STATUS.DEACTIVATED:
                    action = cls.reactivate
                else:
                    action = cls.activate

        LOG.debug("Action %(action)s defined to updates %(updates)s.",
                  {'action': action.__name__, 'updates': values})

        return action

    @classmethod
    def _validate_link(cls, key, value, ctx):
        # check format
        glare_fields.LinkFieldType.coerce(None, key, value)
        # check containment
        if glare_fields.LinkFieldType.is_external(value):
            with urlrequest.urlopen(value) as data:
                data.read(1)
        else:
            filters = [('id', None, 'eq', None, value.split('/')[3])]
            if len(cls.db_api.list(ctx, filters, None, 1, [], False)) == 0:
                raise exception.NotFound

    @classmethod
    def get(cls, context, artifact_id):
        """Return Artifact from Glare repo

        :param context: user context
        :param artifact_id: id of requested artifact
        :return: requested artifact object
        """
        af = cls.db_api.get(context, artifact_id)
        return cls._init_artifact(context, af)

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
            msg = (_("Unsupported filter type '%s(key)'."
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

        new_filters = [('status', None, 'neq', None, cls.STATUS.DELETED)]
        if cls.get_type_name() != 'all':
            new_filters.append(
                ('type_name', None, 'eq', None, cls.get_type_name()))
        if filters is None:
            return new_filters

        for filter_name, filter_value in filters:
            if filter_name in ('tags-any', 'tags'):
                if ':' in filter_value:
                    msg = _("Tags are filtered without operator")
                    raise exception.BadRequest(msg)
                new_filters.append(
                    (filter_name, None, None, None, filter_value))
                continue

            key_name = None
            if '.' in filter_name:
                filter_name, key_name = filter_name.split('.', 1)
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
                if isinstance(field_type, glare_fields.Dict):
                    new_filters.append((
                        filter_name, filter_value, None, None, None))
                else:
                    op, val = utils.split_filter_op(filter_value)
                    cls._validate_filter_ops(filter_name, op)
                    if op == 'in':
                        value = [field_type.coerce(cls(), filter_name, value)
                                 for value in
                                 utils.split_filter_value_for_quotes(val)]
                    else:
                        value = field_type.coerce(cls(), filter_name, val)
                    new_filters.append(
                        (filter_name, key_name, op,
                         cls._get_field_type(field_type), value))
            except ValueError:
                msg = _("Invalid filter value: %s") % str(val)
                raise exception.BadRequest(msg)

        return new_filters

    @classmethod
    def list(cls, context, filters=None, marker=None, limit=None,
             sort=None, latest=False):
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
        :return: list of artifact objects
        """
        if sort is not None:
            sort = cls._parse_sort_values(sort)
        else:
            sort = [('created_at', 'desc', None), ('id', 'asc', None)]

        filters = cls._parse_filter_values(filters)

        return [cls._init_artifact(context, af)
                for af in cls.db_api.list(
                context, filters, marker, limit, sort, latest)]

    @staticmethod
    def _prepare_blob_delete(b, af, name):
        if b['status'] == glare_fields.BlobFieldType.SAVING:
            msg = _('Blob %(name)s is saving for artifact %(id)s'
                    ) % {'name': name, 'id': af.id}
            raise exception.Conflict(msg)
        b['status'] = glare_fields.BlobFieldType.PENDING_DELETE

    @classmethod
    def _delete_blobs(cls, blobs, context, af):
        for name, blob in six.iteritems(blobs):
            if cls.is_blob(name):
                if not blob['external']:
                    try:
                        store_api.delete_blob(blob['url'], context=context)
                    except exception.NotFound:
                        # data has already been remover
                        pass
                cls.db_api.update_blob(context, af.id, {name: None})
            elif cls.is_blob_dict(name):
                upd_blob = deepcopy(blob)
                for key, val in six.iteritems(blob):
                    if not val['external']:
                        try:
                            store_api.delete_blob(val['url'], context=context)
                        except exception.NotFound:
                            pass
                    del upd_blob[key]
                    cls.db_api.update_blob(context, af.id, {name: upd_blob})

    @classmethod
    def delete(cls, context, af):
        """Delete artifact and all its blobs from Glare.

        :param context: user context
        :param af: artifact object targeted for deletion
        """
        # marking artifact as deleted
        cls.db_api.update(context, af.id, {'status': cls.STATUS.DELETED})

        # marking all blobs as pending delete
        blobs = {}
        for name, field in six.iteritems(af.fields):
            if cls.is_blob(name):
                b = getattr(af, name)
                if b:
                    cls._prepare_blob_delete(b, af, name)
                    blobs[name] = b
            elif cls.is_blob_dict(name):
                bd = getattr(af, name)
                if bd:
                    for key, b in six.iteritems(bd):
                        cls._prepare_blob_delete(b, af, name)
                    blobs[name] = bd
        LOG.debug("Marked artifact %(artifact)s as deleted and all its blobs "
                  "%(blobs) as pending delete.",
                  {'artifact': af.id, 'blobs': blobs})
        cls.db_api.update_blob(context, af.id, blobs)

        if not CONF.delayed_blob_delete:
            if blobs:
                # delete blobs one by one
                cls._delete_blobs(blobs, context, af)
                LOG.info(_LI("Blobs successfully deleted "
                             "for artifact %s"), af.id)
            # delete artifact itself
            cls.db_api.delete(context, af.id)

    @classmethod
    def activate(cls, context, af, values):
        """Activate artifact and make it available for usage.

        :param context: user context
        :param af: current artifact object
        :param values: dictionary with changes for artifact
        :return: artifact object with changed status
        """
        # validate that came to artifact as updates
        if values != {'status': cls.STATUS.ACTIVE}:
            msg = _("Only {'status': %s} is allowed in a request "
                    "for activation.") % cls.STATUS.ACTIVE
            raise exception.BadRequest(msg)

        for name, type_obj in six.iteritems(af.fields):
            if type_obj.required_on_activate and getattr(af, name) is None:
                msg = _("'%s' attribute must be set before activation") % name
                raise exception.BadRequest(msg)

        cls.validate_activate(context, af)
        if af.status != cls.STATUS.DRAFTED:
            raise exception.InvalidStatusTransition(
                orig=af.status, new=cls.STATUS.ACTIVE
            )
        LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                     "activate passed for request %(request)s."),
                 {'artifact': af.id, 'request': context.request_id})
        af = cls.db_api.update(context, af.id, {'status': cls.STATUS.ACTIVE})
        return cls._init_artifact(context, af)

    @classmethod
    def reactivate(cls, context, af, values):
        """Make Artifact active after deactivation

        :param context: user context
        :param af: current artifact object
        :param values: dictionary with changes for artifact
        :return: artifact object with changed status
        """
        # validate that came to artifact as updates
        if values != {'status': cls.STATUS.ACTIVE}:
            msg = _("Only {'status': %s} is allowed in a request "
                    "for reactivation.") % cls.STATUS.ACTIVE
            raise exception.BadRequest(msg)
        if af.status != cls.STATUS.DEACTIVATED:
            raise exception.InvalidStatusTransition(
                orig=af.status, new=cls.STATUS.ACTIVE
            )
        LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                     "reactivate passed for request %(request)s."),
                 {'artifact': af.id, 'request': context.request_id})
        af = cls.db_api.update(context, af.id, {'status': cls.STATUS.ACTIVE})
        return cls._init_artifact(context, af)

    @classmethod
    def deactivate(cls, context, af, values):
        """Deny Artifact downloading due to security concerns.

        If user uploaded suspicious artifact then administrators(or other
        users - it depends on policy configurations) can deny artifact data
        to be downloaded by regular users by making artifact deactivated.
        After additional investigation artifact can be reactivated or
        deleted from Glare.

        :param context: user context
        :param af: current artifact object
        :param values: dictionary with changes for artifact
        :return: artifact object with changed status
        """
        if values != {'status': cls.STATUS.DEACTIVATED}:
            msg = _("Only {'status': %s} is allowed in a request "
                    "for deactivation.") % cls.STATUS.DEACTIVATED
            raise exception.BadRequest(msg)

        if af.status != cls.STATUS.ACTIVE:
            raise exception.InvalidStatusTransition(
                orig=af.status, new=cls.STATUS.ACTIVE
            )
        LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                     "deactivate passed for request %(request)s."),
                 {'artifact': af.id, 'request': context.request_id})
        af = cls.db_api.update(context, af.id,
                               {'status': cls.STATUS.DEACTIVATED})
        return cls._init_artifact(context, af)

    @classmethod
    def publish(cls, context, af, values):
        """Make artifact available for all tenants.

        :param context: user context
        :param af: current artifact object
        :param values: dictionary with changes for artifact
        :return: artifact object with changed visibility
        """
        if values != {'visibility': 'public'}:
            msg = _("Only {'visibility': 'public'} is allowed in a request "
                    "for artifact publish.")
            raise exception.BadRequest(msg)

        with cls._get_scoped_lock(af, values):
            if af.status != cls.STATUS.ACTIVE:
                msg = _("Cannot publish non-active artifact")
                raise exception.BadRequest(msg)

            cls._validate_versioning(context, af.name, af.version,
                                     is_public=True)
            cls.validate_publish(context, af)
            LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                         "publish passed for request %(request)s."),
                     {'artifact': af.id, 'request': context.request_id})
            af = cls.db_api.update(context, af.id, {'visibility': 'public'})
            return cls._init_artifact(context, af)

    @classmethod
    def get_max_blob_size(cls, field_name):
        """Get the maximum allowed blob size in bytes.

        :param field_name: blob or blob dict field name
        :return: maximum blob size in bytes
        """
        return getattr(cls.fields[field_name], 'max_blob_size',
                       attribute.BlobAttribute.DEFAULT_MAX_BLOB_SIZE)

    @classmethod
    def validate_upload_allowed(cls, af, field_name, blob_key=None):
        """Validate if given blob is ready for uploading.

        :param af: current artifact object
        :param field_name: blob or blob dict field name
        :param blob_key: indicates key name if field_name is a blob dict
        """

        blob_name = "%s[%s]" % (field_name, blob_key)\
            if blob_key else field_name

        cls._validate_change_allowed([field_name], af,
                                     validate_blob_names=False)
        if blob_key:
            if not cls.is_blob_dict(field_name):
                msg = _("%s is not a blob dict") % field_name
                raise exception.BadRequest(msg)
            if getattr(af, field_name).get(blob_key) is not None:
                msg = (_("Cannot re-upload blob value to blob dict %(blob)s "
                         "with key %(key)s for artifact %(af)s") %
                       {'blob': field_name, 'key': blob_key, 'af': af.id})
                raise exception.Conflict(message=msg)
        else:
            if not cls.is_blob(field_name):
                msg = _("%s is not a blob") % field_name
                raise exception.BadRequest(msg)
            if getattr(af, field_name) is not None:
                msg = _("Cannot re-upload blob %(blob)s for artifact "
                        "%(af)s") % {'blob': field_name, 'af': af.id}
                raise exception.Conflict(message=msg)
        LOG.debug("Parameters validation for artifact %(artifact)s blob "
                  "upload passed for blob %(blob_name)s. "
                  "Start blob uploading to backend.",
                  {'artifact': af.id, 'blob_name': blob_name})

    @classmethod
    def update_blob(cls, context, af_id, field_name, values):
        """Update blob info in database.

        :param context: user context
        :param af_id: id of modified artifact
        :param field_name: blob or blob dict field name
        :param values: updated blob values
        :return updated artifact definition in Glare
        """
        af_upd = cls.db_api.update_blob(context, af_id, {field_name: values})
        return cls._init_artifact(context, af_upd)

    @classmethod
    def validate_activate(cls, context, af, values=None):
        """Validation hook for activation."""
        pass

    @classmethod
    def validate_upload(cls, context, af, field_name, fd):
        """Validation hook for uploading."""
        return fd, None

    @classmethod
    def validate_publish(cls, context, af):
        """Validation hook for publishing."""
        pass

    @classmethod
    def get_default_store(cls, context=None, af=None,
                          field_name=None, blob_key=None):
        """Return a default store type for artifact type."""
        for t in CONF.enabled_artifact_types:
            type_name, __, store_name = t.partition(':')
            if type_name == cls.get_type_name():
                return store_name

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

    def _obj_changes_to_primitive(self):
        changes = self.obj_get_changes()
        res = {}
        for key, val in six.iteritems(changes):
            if val is not None and hasattr(val, 'to_primitive'):
                res[key] = val.to_primitive()
            else:
                res[key] = val
        return res

    @classmethod
    def _schema_attr(cls, attr, attr_name=''):
        attr_type = utils.get_schema_type(attr)
        schema = {}

        # generate schema for validators
        for val in getattr(attr, 'validators', []):
            schema.update(val.to_jsonschema())

        schema['type'] = (attr_type
                          if not attr.nullable else [attr_type, 'null'])
        schema['glareType'] = utils.get_glare_type(attr)
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

        if attr.system:
            schema['readOnly'] = True

        if isinstance(attr, glare_fields.Dict):
            element_type = (utils.get_schema_type(attr.element_type)
                            if hasattr(attr, 'element_type')
                            else 'string')

            if attr.element_type is glare_fields.BlobFieldType:
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
                    schema['properties'] = properties
                    schema['additionalProperties'] = False
                else:
                    schema['additionalProperties'] = {'type': element_type}

        if attr_type == 'array':
            schema['items'] = {
                'type': (utils.get_schema_type(attr.element_type)
                         if hasattr(attr, 'element_type')
                         else 'string')}

        if isinstance(attr, glare_fields.BlobField):
            schema.update(output_blob_schema)

        if isinstance(attr, fields.DateTimeField):
            schema['format'] = 'date-time'

        if attr_name == 'status':
            schema['enum'] = list(
                glare_fields.ArtifactStatusField.ARTIFACT_STATUS)

        if attr.description:
            schema['description'] = attr.description
        if attr.mutable:
            schema['mutable'] = True
        if attr.sortable:
            schema['sortable'] = True
        if not attr.required_on_activate:
            schema['required_on_activate'] = False
        if attr._default is not None:
            schema['default'] = attr._default

        schema['filter_ops'] = attr.filter_ops

        return schema

    @classmethod
    def gen_schemas(cls):
        """Return json schema representation of the artifact type."""
        schemas_prop = {}
        for attr_name, attr in six.iteritems(cls.fields):
            schemas_prop[attr_name] = cls._schema_attr(
                attr, attr_name=attr_name)
        schemas = {'properties': schemas_prop,
                   'name': cls.get_type_name(),
                   'version': cls.VERSION,
                   'title': 'Artifact type %s of version %s' %
                            (cls.get_type_name(), cls.VERSION),
                   'type': 'object',
                   'required': ['name']}

        return schemas
