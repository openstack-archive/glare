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
from oslo_utils import excutils
from oslo_utils import timeutils
from oslo_versionedobjects import base
from oslo_versionedobjects import fields
import six
import six.moves.urllib.request as urlrequest
from webob.multidict import MultiDict

from glare.common import exception
from glare.common import store_api
from glare.common import utils
from glare.db import artifact_api
from glare import locking
from glare.i18n import _, _LI
from glare.objects import attribute
from glare.objects import fields as glare_fields
from glare.objects.fields import BlobFieldType as BlobStatus
from glare.objects import validators

artifact_opts = [
    cfg.BoolOpt('delayed_blob_delete', default=False,
                help=_("Defines if blob must be deleted immediately "
                       "or just marked as deleted so it can be cleaned by some"
                       "other tool in background.")),
]

CONF = cfg.CONF
CONF.register_opts(artifact_opts)

LOG = logging.getLogger(__name__)


class classproperty(property):
    """Special decorator that creates class properties"""

    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()


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

    lock_engine = locking.LockEngine(artifact_api.ArtifactLockApi())
    Field = attribute.Attribute.init
    DictField = attribute.DictAttribute.init
    ListField = attribute.ListAttribute.init
    Blob = attribute.BlobAttribute.init

    fields = {
        'id': Field(fields.StringField, system=True,
                    validators=[validators.UUID()], nullable=False,
                    sortable=True),
        'name': Field(fields.StringField, required_on_activate=False,
                      nullable=False, sortable=True),
        'owner': Field(fields.StringField, system=True,
                       required_on_activate=False, nullable=False,
                       sortable=True),
        'status': Field(glare_fields.ArtifactStatusField,
                        default=glare_fields.ArtifactStatusField.QUEUED,
                        nullable=False, sortable=True),
        'created_at': Field(fields.DateTimeField, system=True,
                            filter_ops=attribute.FILTERS,
                            nullable=False, sortable=True),
        'updated_at': Field(fields.DateTimeField, system=True,
                            filter_ops=attribute.FILTERS,
                            nullable=False, sortable=True),
        'activated_at': Field(fields.DateTimeField, system=True,
                              filter_ops=attribute.FILTERS,
                              required_on_activate=False, sortable=True),
        'description': Field(fields.StringField, mutable=True,
                             required_on_activate=False, default="",
                             validators=[validators.MaxStrLen(4096)],
                             filter_ops=[]),
        'tags': ListField(fields.String, mutable=True,
                          required_on_activate=False,
                          # tags are filtered without any operators
                          filter_ops=[],
                          element_validators=[validators.ForbiddenChars(
                              [',', '/'])]),
        'metadata': DictField(fields.String, required_on_activate=False,
                              element_validators=[validators.MinStrLen(1)],
                              filter_ops=(attribute.FILTER_EQ,
                                          attribute.FILTER_NEQ)),
        'visibility': Field(fields.StringField, default='private',
                            nullable=False, filter_ops=(attribute.FILTER_EQ,),
                            sortable=True),
        'version': Field(glare_fields.VersionField, required_on_activate=False,
                         default=DEFAULT_ARTIFACT_VERSION,
                         filter_ops=attribute.FILTERS, nullable=False,
                         sortable=True, validators=[validators.Version()]),
        'provided_by': DictField(fields.String,
                                 validators=[
                                     validators.AllowedDictKeys(
                                         ("name", "href", "company")),
                                     validators.RequiredDictKeys(
                                         ("name", "href", "company"))
                                 ],
                                 default=None,
                                 required_on_activate=False),
        'supported_by': DictField(fields.String,
                                  validators=[
                                      validators.RequiredDictKeys(("name",))
                                  ],
                                  default=None,
                                  required_on_activate=False),
        'release': ListField(fields.String,
                             validators=[validators.Unique()],
                             required_on_activate=False),
        'icon': Blob(required_on_activate=False),
        'license': Field(fields.StringField,
                         required_on_activate=False),
        'license_url': Field(fields.StringField,
                             required_on_activate=False),
    }

    @classmethod
    def is_blob(cls, field_name):
        """Helper to check that field is blob

        :param field_name: name of field
        :return: True if field is a blob, False otherwise
        """
        return isinstance(cls.fields.get(field_name), glare_fields.BlobField)

    @classmethod
    def is_blob_dict(cls, field_name):
        """Helper to check that field is blob dict

        :param field_name: name of field
        :return: True if field is a blob dict, False otherwise
        """
        return (isinstance(cls.fields.get(field_name), glare_fields.Dict) and
                cls.fields[field_name].element_type ==
                glare_fields.BlobFieldType)

    @classmethod
    def _init_artifact(cls, context, values):
        """Initialize an empty versioned object with values

        Initialize vo object with default values and values specified by user.
        Also reset all changes for initialized object so user of the method
        can track own changes.

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
        for name, value in six.iteritems(values):
            setattr(af, name, value)
        return af

    @classmethod
    def get_type_name(cls):
        """Return type name that allows to find Artifact Type in Glare

        Type name allows to find Artifact Type definition in Glare registry
        so Engine can instantiate Artifacts. Artifact also becomes available
        with artifact type in Glare API.
        For example, when get_type_name returns 'my_artifact' then
        users can list artifacts by GET <host_name>/v1/artifacts/my_artifact.
        This type name is also used in glare configuration when turning on/off
        specific Artifact Types.
        :return: string that identifies current Artifact Type.
        """
        raise NotImplementedError()

    _DB_API = None

    @classmethod
    def init_db_api(cls):
        """Provide initialized db api to interact with artifact database.

        To interact with database each artifact type must provide an api
        to execute db operations with artifacts.
        :return: subtype of glance.db.glare.api.BaseDBAPI
        """
        return artifact_api.ArtifactAPI(cls)

    @classproperty
    def db_api(cls):
        """Return current database API"""
        if cls._DB_API is None:
            cls._DB_API = cls.init_db_api()
        return cls._DB_API

    @classmethod
    def _get_versioning_scope(cls, context, values, af=None):
        """Return identifier that allows to track versioning in Glare.

        The method returns unique identifier for artifact version. So two
        artifact with the same version and scope returns the same identifier.
        It allows to specify lock for artifact version when creating or
        updating artifact.

        :param context: user context
        :param af: actual artifact values(if present)
        :param values: values proposed for artifact update
        :return: versioning scope id or None if there is no scope for locking
        """
        name = values.get('name')
        version = values.get('version')
        visibility = values.get('visibility')

        if (name, version, visibility) == (None, None, None):
            # no versioning changes here == no lock scope
            return None

        if af:
            if name is None:
                name = af.name
            version = version or af.version
            visibility = visibility or af.visibility

        if name:
            scope_id = "%s:%s" % (name, str(
                version or cls.DEFAULT_ARTIFACT_VERSION))
            if visibility == 'public':
                scope_id += ':%s' % str(context.tenant)
            return scope_id

    @classmethod
    def create(cls, context, values):
        """Create new Artifact in Glare repo

        :param context: user context
        :param values: Dict with specified artifact properties
        :return: definition of create Artifact
        """
        if context.tenant is None or context.read_only:
            msg = _("It's forbidden to anonymous users to create artifacts.")
            raise exception.Forbidden(msg)
        else:
            with cls.lock_engine.acquire(
                    context, cls._get_versioning_scope(context, values)):
                ver = values.setdefault(
                    'version', cls.DEFAULT_ARTIFACT_VERSION)
                cls._validate_versioning(context, values.get('name'), ver)
                # validate other values
                cls._validate_input_values(context, values)
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
                af_vals = cls.db_api.create(context,
                                            af.obj_changes_to_primitive())
                return cls._init_artifact(context, af_vals)

    @classmethod
    def _validate_versioning(cls, context, name, version, is_public=False):
        if version is not None and name not in (None, ""):
            filters = {'name': name, 'version': version,
                       'status': 'neq:deleted'}
            if is_public is False:
                filters.update({'owner': context.tenant,
                                'visibility': 'private'})
            else:
                filters.update({'visibility': 'public'})
            if len(cls.list(context, MultiDict(filters))) > 0:
                msg = _("Artifact with this name and version is already "
                        "exists for this owner.")
                raise exception.Conflict(msg)
        else:
            msg = _("Cannot set artifact version without name and version.")
            raise exception.BadRequest(msg)

    @classmethod
    def _validate_input_values(cls, context, values):
        # validate that we are not specifying any system attribute
        # and that we do not upload blobs or add locations here
        for field_name in values:
            if field_name in cls.fields:
                if cls.fields[field_name].system is True:
                    msg = _("Cannot specify system property %s. It is not "
                            "available for modifying by users.") % field_name
                    raise exception.Forbidden(msg)
                elif cls.is_blob(field_name) or cls.is_blob_dict(field_name):
                    msg = _("Cannot add blob %s with this request. "
                            "Use special Blob API for that.") % field_name
                    raise exception.BadRequest(msg)
            else:
                msg = (_("Cannot add non-existing property %s to artifact. ")
                       % field_name)
                raise exception.BadRequest(msg)

    @classmethod
    def _validate_update_allowed(cls, context, af, field_names):
        """Validate if fields can be updated in artifact

        :param context:
        :param af:
        :param field_names:
        :return:
        """
        if af.status not in (cls.STATUS.ACTIVE, cls.STATUS.QUEUED):
            msg = _("Forbidden to change attributes "
                    "if artifact not active or queued.")
            raise exception.Forbidden(message=msg)

        for field_name in field_names:
            field = cls.fields[field_name]
            if field.system is True:
                msg = _("Cannot specify system property %s. It is not "
                        "available for modifying by users.") % field_name
                raise exception.Forbidden(msg)
            if af.status == cls.STATUS.ACTIVE and not field.mutable:
                msg = (_("Forbidden to change property '%s' after activation.")
                       % field_name)
                raise exception.Forbidden(message=msg)

    @classmethod
    def update(cls, context, af, values):
        """Update Artifact in Glare repo

        :param context: user Context
        :param af: current definition of Artifact in Glare
        :param values: list of changes for artifact
        :return: definition of updated Artifact
        """
        # reset all changes of artifact to reuse them after update
        af.obj_reset_changes()
        scope = cls._get_versioning_scope(context, values, af)
        with cls.lock_engine.acquire(context, scope):
            # validate version
            if 'name' in values or 'version' in values:
                new_name = values.get('name') or af.name
                new_version = values.get('version') or af.version
                cls._validate_versioning(context, new_name, new_version)

            # validate other values
            cls._validate_update_allowed(context, af, list(values))
            cls._validate_input_values(context, values)
            # apply values to the artifact. if all changes applied then update
            # values in db or raise an exception in other case.
            for key, value in six.iteritems(values):
                setattr(af, key, value)

            LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                         "update passed for request %(request)s."),
                     {'artifact': af.id, 'request': context.request_id})
            updated_af = cls.db_api.update(
                context, af.id, af.obj_changes_to_primitive())
            return cls._init_artifact(context, updated_af)

    @classmethod
    def get_action_for_updates(cls, context, artifact, updates, registry):
        """The method defines how to detect appropriate action based on update

        Validate request for update and determine if it is request for action.
        Also do a validation for request for action if it is an action.

        :return: action reference for updates dict
        """
        action = cls.update
        if 'visibility' in updates:
            # validate publish action format
            action = cls.publish
        elif 'status' in updates:
            status = updates['status']
            if status == cls.STATUS.DEACTIVATED:
                action = cls.deactivate
            elif status == cls.STATUS.ACTIVE:
                if artifact.status == artifact.STATUS.DEACTIVATED:
                    action = cls.reactivate
                else:
                    action = cls.activate

        # check updates for dependencies and validate them
        try:
            for key, value in six.iteritems(updates):
                if cls.fields.get(key) is glare_fields.Dependency \
                        and value is not None:
                    # check format
                    glare_fields.DependencyFieldType.coerce(None, key, value)
                    # check containment
                    if glare_fields.DependencyFieldType.is_external(value):
                        # validate external dependency
                        cls._validate_external_dependency(value)
                    else:
                        type_name = (glare_fields.DependencyFieldType.
                                     get_type_name(value))
                        af_type = registry.get_artifact_type(type_name)
                        cls._validate_soft_dependency(context, value, af_type)
        except Exception as e:
            msg = (_("Bad dependency in artifact %(af)s: %(msg)s")
                   % {"af": artifact.id, "msg": str(e)})
            raise exception.BadRequest(msg)

        LOG.debug("Action %(action)s defined to updates %(updates)s.",
                  {'action': action.__name__, 'updates': updates})

        return action

    @classmethod
    def _validate_external_dependency(cls, link):
        with urlrequest.urlopen(link) as data:
            data.read(1)

    @classmethod
    def _validate_soft_dependency(cls, context, link, af_type):
        af_id = link.split('/')[3]
        af_type.get(context, af_id)

    @classmethod
    def get(cls, context, artifact_id):
        """Return Artifact from Glare repo

        :param context: user context
        :param artifact_id: id of requested Artifact
        :return: Artifact definition
        """
        af = cls.db_api.get(context, artifact_id)
        if af['status'] == cls.STATUS.DELETED:
            raise exception.ArtifactNotFound(
                type_name=cls.get_type_name(), id=artifact_id)
        return cls._init_artifact(context, af)

    @classmethod
    def _get_field_type(cls, obj):
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
    def _validate_filter_name(cls, filter_name):
        if cls.fields.get(filter_name) is None:
            msg = _("Unable filter '%s'") % filter_name
            raise exception.BadRequest(msg)

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
        # we use next format for filters:
        # (field_name, key_name, op, field_type, value)
        new_filters = []
        for filter_name, filter_value in six.iteritems(filters):
            key_name = None
            if filter_name in ('tags-any', 'tags'):
                if ':' in filter_value:
                    msg = _("Tags are filtered without operator")
                    raise exception.BadRequest(msg)
                new_filters.append(
                    (filter_name, None, None, None, filter_value))
                continue
            elif '.' in filter_name:
                filter_name, key_name = filter_name.split('.', 1)
                cls._validate_filter_name(filter_name)
                op, val = utils.split_filter_op(filter_value)
                cls._validate_filter_ops(filter_name, op)
                field_type = cls.fields.get(filter_name).element_type
            else:
                cls._validate_filter_name(filter_name)
                op, val = utils.split_filter_op(filter_value)
                cls._validate_filter_ops(filter_name, op)
                field_type = cls.fields.get(filter_name)

            try:
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
             sort=None):
        """List all available Artifacts in Glare repo

        :param context: user context
        :param filters: filtering conditions to Artifact list
        :param marker: id of Artifact that identifies where Glare should
        start listing Artifacts. So all Artifacts before that Artifact in
        resulting list must be ignored. It is useful for Artifact pagination.
        :param limit: maximum number of Artifact items in list.
        :param sort: sorting preferences when requesting Artifact list.
        :return: list of Artifacts
        """
        if sort is not None:
            sort = cls._parse_sort_values(sort)
        else:
            sort = [('created_at', 'desc', None), ('id', 'asc', None)]

        if filters is not None:
            filters = cls._parse_filter_values(filters)
        else:
            filters = []

        return [cls._init_artifact(context, af)
                for af in cls.db_api.list(
                context, filters, marker, limit, sort)]

    @classmethod
    def delete(cls, context, af):
        """Delete Artifact and all blobs from Glare.

        :param context: user context
        :param af: definition of artifact targeted to delete
        """
        if af.visibility == 'public' and not context.is_admin:
            msg = _("Only admins are allowed to delete public images")
            raise exception.Forbidden(msg)
        # marking all blobs as pending delete
        blobs = {}
        for name, field in six.iteritems(af.fields):
            if cls.is_blob(name):
                b = getattr(af, name)
                if b:
                    if b['status'] == BlobStatus.PENDING_DELETE:
                        msg = _('Blob %(name)s is already deleting '
                                'for artifact %(id)s') % {'name': name,
                                                          'id': af.id}
                        raise exception.Conflict(msg)
                    else:
                        b['status'] = BlobStatus.PENDING_DELETE
                        blobs[name] = b
            elif cls.is_blob_dict(name):
                bd = getattr(af, name)
                if bd:
                    for key, b in six.iteritems(bd):
                        if b['status'] == BlobStatus.PENDING_DELETE:
                            msg = _('Blob %(name)s is already deleting '
                                    'for artifact %(id)s') % {'name': name,
                                                              'id': af.id}
                            raise exception.Conflict(msg)
                        else:
                            b['status'] = BlobStatus.PENDING_DELETE
                    blobs[name] = bd
        if blobs:
            LOG.debug("Marked all blobs %(blobs) for artifact %(artifact)s "
                      "as pending delete. Start blobs delete.",
                      {'blobs': blobs, 'artifact': af.id})
            cls.db_api.update(context, af.id, blobs)
            # delete blobs one by one
            if not CONF.delayed_blob_delete:
                for name, blob in six.iteritems(blobs):
                    if cls.is_blob(name):
                        store_api.delete_blob(blob['url'], context=context)
                        cls.db_api.update(context, af.id, {name: None})
                    elif cls.is_blob_dict(name):
                        upd_blob = deepcopy(blob)
                        for key, val in six.iteritems(blob):
                            store_api.delete_blob(val['url'], context=context)
                            del upd_blob[key]
                            cls.db_api.update(context, af.id, {name: upd_blob})

            LOG.info(_LI("Blobs successfully deleted for artifact %s"), af.id)
        # delete artifact itself
        cls.db_api.delete(context, af.id)

    @classmethod
    def activate(cls, context, af, values):
        """Activate Artifact and make it available for users

        :param context: User Context
        :param af: current Artifact definition in Glare
        :return: definition of activated Artifact
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
        if af.status != cls.STATUS.QUEUED:
            raise exception.InvalidStatusTransition(
                orig=af.status, new=cls.STATUS.ACTIVE
            )
        LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                     "activate passed for request %(request)s."),
                 {'artifact': af.id, 'request': context.request_id})
        active_af = cls.db_api.update(context, af.id, values)
        return cls._init_artifact(context, active_af)

    @classmethod
    def reactivate(cls, context, af, values):
        """Make Artifact active after de-activation

        :param context: user context
        :param af: definition of de-activated Artifact
        :return: definition of active Artifact
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
        af = cls.db_api.update(context, af.id, values)
        return cls._init_artifact(context, af)

    @classmethod
    def deactivate(cls, context, af, values):
        """Deny Artifact downloading due to security concerns

        If user uploaded suspicious Artifact then Cloud Admins(or other users -
        it depends on policy configurations) can deny Artifact download by
        users by making Artifact de-activated. After additional investigation
        Artifact can be re-activated or deleted from Glare.

        :param context: user context
        :param af: Artifact definition in Glare
        :return: definition of de-activated Artifact
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
        af = cls.db_api.update(context, af.id, values)
        return cls._init_artifact(context, af)

    @classmethod
    def publish(cls, context, af, values):
        """Make Artifact available for everyone

        :param context: user context
        :param af: definition of published Artifact
        :return: definition of active Artifact
        """
        if values != {'visibility': 'public'}:
            msg = _("Only {'visibility': 'public'} is allowed in a request "
                    "for artifact publish.")
            raise exception.BadRequest(msg)

        with cls.lock_engine.acquire(context, cls._get_versioning_scope(
                context, values, af)):
            if af.status != cls.STATUS.ACTIVE:
                msg = _("Cannot publish non-active artifact")
                raise exception.BadRequest(msg)

            cls._validate_versioning(context, af.name, af.version,
                                     is_public=True)
            cls.validate_publish(context, af)
            LOG.info(_LI("Parameters validation for artifact %(artifact)s "
                         "publish passed for request %(request)s."),
                     {'artifact': af.id, 'request': context.request_id})
            af = cls.db_api.update(context, af.id, values)
            return cls._init_artifact(context, af)

    @classmethod
    def _get_max_blob_size(cls, field_name):
        return getattr(cls.fields[field_name], 'max_blob_size',
                       attribute.BlobAttribute.DEFAULT_MAX_BLOB_SIZE)

    @classmethod
    def _validate_upload_allowed(cls, context, af, field_name, blob_key=None):
        if field_name not in cls.fields:
            msg = _("%s property does not exist") % field_name
            raise exception.BadRequest(msg)
        cls._validate_update_allowed(context, af, [field_name])
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

    @classmethod
    def upload_blob(cls, context, af, field_name, fd, content_type):
        """Upload binary object as artifact property

        :param context: user context
        :param af: current Artifact definition
        :param field_name: name of blob field
        :param fd: file descriptor that Glare uses to upload the file
        :param content_type: data content-type
        :return: updated Artifact definition in Glare
        """
        fd = cls.validate_upload(context, af, field_name, fd)
        cls._validate_upload_allowed(context, af, field_name)

        LOG.debug("Parameters validation for artifact %(artifact)s blob "
                  "upload passed for blob %(blob)s. "
                  "Start blob uploading to backend.",
                  {'artifact': af.id, 'blob': field_name})
        blob = {'url': None, 'size': None, 'checksum': None,
                'status': BlobStatus.SAVING, 'external': False,
                'content_type': content_type}
        setattr(af, field_name, blob)
        cls.db_api.update(
            context, af.id, {field_name: getattr(af, field_name)})
        blob_id = getattr(af, field_name)['id']

        try:
            location_uri, size, checksum = store_api.save_blob_to_store(
                blob_id, fd, context, cls._get_max_blob_size(field_name))
            blob.update({'url': location_uri, 'status': BlobStatus.ACTIVE,
                         'size': size, 'checksum': checksum})
            setattr(af, field_name, blob)
            af_upd = cls.db_api.update(
                context, af.id, {field_name: getattr(af, field_name)})
            LOG.info(_LI("Successfully finished blob upload for artifact "
                         "%(artifact)s blob field %(blob)s."),
                     {'artifact': af.id, 'blob': field_name})
            return cls._init_artifact(context, af_upd)
        except Exception:
            with excutils.save_and_reraise_exception(logger=LOG):
                cls.db_api.update(context, af.id, {field_name: None})

    @classmethod
    def download_blob(cls, context, af, field_name):
        """Download binary data from Glare Artifact.

        :param context: user context
        :param af: Artifact definition in Glare repo
        :param field_name: name of blob field
        :return: file iterator for requested file
        """
        if not cls.is_blob(field_name):
            msg = _("%s is not a blob") % field_name
            raise exception.BadRequest(msg)
        if af.status == cls.STATUS.DEACTIVATED and not context.is_admin:
            msg = _("Only admin is allowed to download image data "
                    "when it's deactivated")
            raise exception.Forbidden(message=msg)
        blob = getattr(af, field_name)
        if blob is None or blob['status'] != BlobStatus.ACTIVE:
            msg = _("%s is not ready for download") % field_name
            raise exception.BadRequest(message=msg)
        meta = {'checksum': blob.get('checksum'),
                'external': blob.get('external')}
        if blob['external']:
            data = {'url': blob['url']}
        else:
            data = store_api.load_from_store(uri=blob['url'], context=context)
            meta['size'] = blob.get('size')
            meta['content_type'] = blob.get('content_type')
        return data, meta

    @classmethod
    def upload_blob_dict(cls, context, af, field_name, blob_key, fd,
                         content_type):
        """Upload binary object as artifact property

        :param context: user context
        :param af: current Artifact definition
        :param blob_key: name of blob key in dict
        :param fd: file descriptor that Glare uses to upload the file
        :param field_name: name of blob dict field
        :param content_type: data content-type
        :return: updated Artifact definition in Glare
        """
        fd = cls.validate_upload(context, af, field_name, fd)
        cls._validate_upload_allowed(context, af, field_name, blob_key)

        LOG.debug("Parameters validation for artifact %(artifact)s blob "
                  "upload passed for blob dict  %(blob)s with key %(key)s. "
                  "Start blob uploading to backend.",
                  {'artifact': af.id, 'blob': field_name, 'key': blob_key})
        blob = {'url': None, 'size': None, 'checksum': None,
                'status': BlobStatus.SAVING, 'external': False,
                'content_type': content_type}
        blob_dict_attr = getattr(af, field_name)
        blob_dict_attr[blob_key] = blob
        cls.db_api.update(
            context, af.id, {field_name: blob_dict_attr})
        blob_id = getattr(af, field_name)[blob_key]['id']
        try:
            location_uri, size, checksum = store_api.save_blob_to_store(
                blob_id, fd, context, cls._get_max_blob_size(field_name))
            blob.update({'url': location_uri, 'status': BlobStatus.ACTIVE,
                         'size': size, 'checksum': checksum})
            af_values = cls.db_api.update(
                context, af.id, {field_name: blob_dict_attr})
            LOG.info(_LI("Successfully finished blob upload for artifact "
                         "%(artifact)s blob dict field %(blob)s with key."),
                     {'artifact': af.id, 'blob': field_name, 'key': blob_key})
            return cls._init_artifact(context, af_values)
        except Exception:
            with excutils.save_and_reraise_exception(logger=LOG):
                del blob_dict_attr[blob_key]
                cls.db_api.update(context, af.id, {field_name: blob_dict_attr})

    @classmethod
    def download_blob_dict(cls, context, af, field_name, blob_key):
        """Download binary data from Glare Artifact.

        :param context: user context
        :param af: Artifact definition in Glare repo
        :param blob_key: name of blob key in dict
        :param field_name: name of blob dict field
        :return: file iterator for requested file
        """
        if not cls.is_blob_dict(field_name):
            msg = _("%s is not a blob dict") % field_name
            raise exception.BadRequest(msg)

        if af.status == cls.STATUS.DEACTIVATED and not context.is_admin:
            msg = _("Only admin is allowed to download image data "
                    "when it's deactivated")
            raise exception.Forbidden(message=msg)
        try:
            blob = getattr(af, field_name)[blob_key]
        except KeyError:
            msg = _("Blob with name %(blob_name)s is not found in blob "
                    "dictionary %(blob_dict)s") % (blob_key, field_name)
            raise exception.NotFound(message=msg)
        if blob is None or blob['status'] != BlobStatus.ACTIVE:
            msg = _("Blob %(blob_name)s from blob dictionary %(blob_dict)s "
                    "is not ready for download") % (blob_key, field_name)
            LOG.error(msg)
            raise exception.BadRequest(message=msg)
        meta = {'checksum': blob.get('checksum'),
                'external': blob.get('external')}
        if blob['external']:
            data = {'url': blob['url']}
        else:
            data = store_api.load_from_store(uri=blob['url'], context=context)
            meta['size'] = blob.get('size')
            meta['content_type'] = blob.get('content_type')
        return data, meta

    @classmethod
    def add_blob_location(cls, context, af, field_name, location, blob_meta):
        """Upload binary object as artifact property

        :param context: user context
        :param af: current Artifact definition
        :param field_name: name of blob field
        :param location: blob url
        :return: updated Artifact definition in Glare
        """
        cls._validate_upload_allowed(context, af, field_name)
        LOG.debug("Parameters validation for artifact %(artifact)s location "
                  "passed for blob %(blob)s. Start location check for artifact"
                  ".", {'artifact': af.id, 'blob': field_name})

        blob = {'url': location, 'size': None, 'checksum': None,
                'status': BlobStatus.ACTIVE, 'external': True,
                'content_type': None}

        if blob_meta.get('checksum') is None:
            msg = (_("Incorrect blob metadata %(meta)s. Checksum is required "
                     "for external location in artifact blob %(field_name)."),
                   {"meta": str(blob_meta), "field_name": field_name})
            raise exception.BadRequest(msg)
        else:
            blob['checksum'] = blob_meta['checksum']

        setattr(af, field_name, blob)
        updated_af = cls.db_api.update(
            context, af.id, {field_name: getattr(af, field_name)})
        LOG.info(_LI("External location %(location)s has been created "
                     "successfully for artifact %(artifact)s blob %(blob)s"),
                 {'location': location, 'artifact': af.id,
                  'blob': field_name})
        return cls._init_artifact(context, updated_af)

    @classmethod
    def add_blob_dict_location(cls, context, af, field_name,
                               blob_key, location, blob_meta):
        cls._validate_upload_allowed(context, af, field_name, blob_key)

        blob = {'url': location, 'size': None, 'checksum': None,
                'status': BlobStatus.ACTIVE, 'external': True,
                'content_type': None}

        if blob_meta.get('checksum') is None:
            msg = (_("Incorrect blob metadata %(meta)s. Checksum is required "
                     "for external location in artifact blob "
                     "%(field_name)[%(blob_key)s]."),
                   {"meta": str(blob_meta), "field_name": field_name,
                    "blob_key": str(blob_key)})
            raise exception.BadRequest(msg)
        else:
            blob['checksum'] = blob_meta['checksum']

        blob_dict_attr = getattr(af, field_name)
        blob_dict_attr[blob_key] = blob
        updated_af = cls.db_api.update(
            context, af.id, {field_name: blob_dict_attr})

        LOG.info(
            _LI("External location %(location)s has been created successfully "
                "for artifact %(artifact)s blob dict %(blob)s with key "
                "%(key)s"),
            {'location': location, 'artifact': af.id,
             'blob': field_name, 'key': blob_key})
        return cls._init_artifact(context, updated_af)

    @classmethod
    def validate_activate(cls, context, af, values=None):
        pass

    @classmethod
    def validate_upload(cls, context, af, field_name, fd):
        return fd

    @classmethod
    def validate_publish(cls, context, af):
        pass

    def to_notification(self):
        """Return notification body that can be send to listeners

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
        """Convert oslo versioned object to dictionary

        :return: dict with field names and field values
        """
        return self.obj_to_primitive()['versioned_object.data']

    def obj_changes_to_primitive(self):
        changes = self.obj_get_changes()
        res = {}
        for key, val in six.iteritems(changes):
            if val is not None and hasattr(val, 'to_primitive'):
                res[key] = val.to_primitive()
            else:
                res[key] = val
        return res

    @staticmethod
    def schema_type(attr):
        if isinstance(attr, fields.IntegerField):
            return 'integer'
        elif isinstance(attr, fields.FloatField):
            return 'number'
        elif isinstance(attr, fields.BooleanField):
            return 'boolean'
        elif isinstance(attr, glare_fields.List):
            return 'array'
        elif isinstance(attr, (glare_fields.Dict, glare_fields.BlobField)):
            return 'object'
        return 'string'

    @classmethod
    def schema_attr(cls, attr, attr_name=''):
        attr_type = cls.schema_type(attr)
        schema = {}

        # generate schema for validators
        for val in getattr(attr, 'validators', []):
            schema.update(val.to_jsonschema())

        schema['type'] = (attr_type
                          if not attr.nullable else [attr_type, 'null'])
        output_blob_schema = {
            'type': ['object', 'null'],
            'properties': {
                'size': {'type': ['number', 'null']},
                'checksum': {'type': ['string', 'null']},
                'external': {'type': 'boolean'},
                'status': {'type': 'string',
                           'enum': list(
                               glare_fields.BlobFieldType.BLOB_STATUS)},
                'content_type': {'type': 'string'},
            },
            'required': ['size', 'checksum', 'external', 'status',
                         'content_type'],
            'additionalProperties': False
        }

        if attr.system:
            schema['readOnly'] = True

        if isinstance(attr, glare_fields.Dict):
            element_type = (cls.schema_type(attr.element_type)
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
                'type': (cls.schema_type(attr.element_type)
                         if hasattr(attr, 'element_type')
                         else 'string')}

        if isinstance(attr, glare_fields.BlobField):
            schema.update(output_blob_schema)

        if isinstance(attr, fields.DateTimeField):
            schema['format'] = 'date-time'

        if attr_name == 'status':
            schema['enum'] = list(
                glare_fields.ArtifactStatusField.ARTIFACT_STATUS)

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
        schemas_prop = {}
        for attr_name, attr in six.iteritems(cls.fields):
            schemas_prop[attr_name] = cls.schema_attr(attr,
                                                      attr_name=attr_name)
        schemas = {'properties': schemas_prop,
                   'name': cls.get_type_name(),
                   'title': 'Artifact type %s of version %s' %
                            (cls.get_type_name(), cls.VERSION),
                   'type': 'object',
                   'required': ['name']}

        return schemas
