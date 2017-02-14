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

import copy
import os

import jsonpatch
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from glare.common import exception
from glare.common import policy
from glare.common import store_api
from glare.common import utils
from glare.i18n import _, _LI, _LW
from glare.notification import Notifier
from glare.objects import base
from glare.objects.meta import fields as glare_fields
from glare.objects.meta import registry

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Engine(object):
    """Engine is responsible for executing different helper operations when
    processing incoming requests from Glare API.
    Engine receives incoming data and does the following:
    - check basic policy permissions;
    - requests artifact definition from artifact type registry;
    - check access permission(ro, rw);
    - lock artifact for update if needed;
    - pass data to base artifact to execute all business logic operations
      with database;
    - notify other users about finished operation.
    Engine should not include any business logic and validation related
    to Artifacts. Engine should not know any internal details of artifact
    type, because this part of the work is done by Base artifact type.
    """
    def __init__(self):
        # register all artifact types
        registry.ArtifactRegistry.register_all_artifacts()

    @classmethod
    def _get_schemas(cls, reg):
        if getattr(cls, 'schemas', None):
            pass
        else:
            schemas = {}
            for name, type_list in reg.obj_classes().items():
                type_name = type_list[0].get_type_name()
                schemas[type_name] = \
                    reg.get_artifact_type(type_name).gen_schemas()
            setattr(cls, 'schemas', schemas)
        return copy.deepcopy(cls.schemas)

    @classmethod
    def _get_artifact(cls, context, type_name, artifact_id,
                      read_only=False):
        """Return artifact requested by user.
        Check access permissions and policies.

        :param context: user context
        :param type_name: artifact type name
        :param artifact_id: id of the artifact to be updated
        :param read_only: flag, if set to True only read access is checked,
        if False then engine checks if artifact can be modified by the user
        """

        def _check_read_write_access(ctx, af):
            """Check if artifact can be modified by user.

            :param ctx: user context
            :param af: artifact definition
            :raise: Forbidden if access is not allowed
            """
            if not ctx.is_admin and ctx.tenant != af.owner or ctx.read_only:
                raise exception.Forbidden()

        def _check_read_only_access(ctx, af):
            """Check if user has read only access to artifact.

            :param ctx: user context
            :param af: artifact definition
            :raise: Forbidden if access is not allowed
            """
            private = af.visibility != 'public'
            if (private and
                    not ctx.is_admin and ctx.tenant != af.owner):
                # TODO(kairat): check artifact sharing here
                raise exception.Forbidden()

        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        # only artifact is available for class users
        artifact = artifact_type.get(context, artifact_id)
        if read_only:
            _check_read_only_access(context, artifact)
            LOG.debug("Artifact %s acquired for read-only access", artifact_id)
        else:
            _check_read_write_access(context, artifact)
            LOG.debug("Artifact %s acquired for read-write access",
                      artifact_id)
        return artifact

    @classmethod
    def list_type_schemas(cls, context):
        policy.authorize("artifact:type_list", {}, context)
        return cls._get_schemas(registry.ArtifactRegistry)

    @classmethod
    def show_type_schema(cls, context, type_name):
        policy.authorize("artifact:type_list", {}, context)
        schemas = cls._get_schemas(registry.ArtifactRegistry)
        if type_name not in schemas:
            msg = _("Artifact type %s does not exist") % type_name
            raise exception.NotFound(message=msg)
        return schemas[type_name]

    @classmethod
    def create(cls, context, type_name, values):
        """Create artifact record in Glare.

        :param context: user context
        :param type_name: artifact type name
        :param values: dict with artifact fields
        :return: dict representation of created artifact
        """
        action_name = "artifact:create"
        policy.authorize(action_name, values, context)
        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        # acquire version lock and execute artifact create
        af = artifact_type.create(context, values)
        # notify about new artifact
        Notifier.notify(context, action_name, af)
        # return artifact to the user
        return af.to_dict()

    @classmethod
    def update(cls, context, type_name, artifact_id, patch):
        """Update artifact with json patch.

        Apply patch to artifact and validate artifact before updating it
        in database. If there is request for visibility or status change
        then call specific method for that.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param patch: json patch object
        :return: dict representation of updated artifact
        """

        def _get_updates(af_dict, patch_with_upd):
            """Get updated values for artifact and json patch.

            :param af_dict: current artifact definition as dict
            :param patch_with_upd: json-patch object
            :return dict of updated attributes and their values
            """
            try:
                af_dict_patched = patch_with_upd.apply(af_dict)
                diff = utils.DictDiffer(af_dict_patched, af_dict)

                # we mustn't add or remove attributes from artifact
                if diff.added() or diff.removed():
                    msg = _(
                        "Forbidden to add or remove attributes from artifact. "
                        "Added attributes %(added)s. "
                        "Removed attributes %(removed)s") % {
                        'added': diff.added(), 'removed': diff.removed()
                    }
                    raise exception.BadRequest(message=msg)

                return {key: af_dict_patched[key] for key in diff.changed()}

            except (jsonpatch.JsonPatchException,
                    jsonpatch.JsonPointerException,
                    KeyError) as e:
                raise exception.BadRequest(message=str(e))
            except TypeError as e:
                msg = _("Incorrect type of the element. Reason: %s") % str(e)
                raise exception.BadRequest(msg)
        lock_key = "%s:%s:" % (type_name, artifact_id)
        with base.BaseArtifact.lock_engine.acquire(context, lock_key):
            artifact = cls._get_artifact(context, type_name, artifact_id)
            af_dict = artifact.to_dict()
            updates = _get_updates(af_dict, patch)
            LOG.debug("Update diff successfully calculated for artifact "
                      "%(af)s %(diff)s", {'af': artifact_id, 'diff': updates})

            if not updates:
                return af_dict
            else:
                action = artifact.get_action_for_updates(
                    context, artifact, updates, registry.ArtifactRegistry)
                LOG.debug("Action %(action)s was defined to values %(val)s.",
                          {'action': action.__name__, 'val': updates})
                action_name = "artifact:%s" % action.__name__
                policy.authorize(action_name, af_dict, context)
                modified_af = action(context, artifact, updates)
                Notifier.notify(context, action_name, modified_af)
                return modified_af.to_dict()

    @classmethod
    def get(cls, context, type_name, artifact_id):
        """Show detailed artifact info.

        :param context: user context
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to show
        :return: definition of requested artifact
        """
        policy.authorize("artifact:get", {}, context)
        af = cls._get_artifact(context, type_name, artifact_id,
                               read_only=True)
        return af.to_dict()

    @classmethod
    def list(cls, context, type_name, filters, marker=None, limit=None,
             sort=None, latest=False):
        """Return list of artifacts requested by user.

        :param context: user context
        :param type_name: Artifact type name
        :param filters: filters that need to be applied to artifact
        :param marker: the artifact that considered as begin of the list
        so all artifacts before marker (including marker itself) will not be
        added to artifact list
        :param limit: maximum number of items in list
        :param sort: sorting options
        :param latest: flag that indicates, that only artifacts with highest
        versions should be returned in output
        :return: list of artifact definitions
        """
        policy.authorize("artifact:list", {}, context)
        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        # return list to the user
        af_list = [af.to_dict()
                   for af in artifact_type.list(context, filters, marker,
                                                limit, sort, latest)]
        return af_list

    @classmethod
    def delete(cls, context, type_name, artifact_id):
        """Delete artifact from Glare.

        :param context: User context
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to delete
        """
        af = cls._get_artifact(context, type_name, artifact_id)
        policy.authorize("artifact:delete", af.to_dict(), context)
        af.delete(context, af)
        Notifier.notify(context, "artifact.delete", af)

    @classmethod
    def add_blob_location(cls, context, type_name, artifact_id, field_name,
                          location, blob_meta, blob_key=None):
        """Add external location to blob.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param field_name: name of blob or blob dict field
        :param location: external blob url
        :param blob_meta: dictionary containing blob metadata like md5 checksum
        :param blob_key: if field_name is blob dict it specifies key
        in this dict
        :return: dict representation of updated artifact
        """
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = 'artifact:set_location'
        policy.authorize(action_name, af.to_dict(), context)

        blob_name = "%s[%s]" % (field_name, blob_key)\
            if blob_key else field_name

        blob = {'url': location, 'size': None, 'md5': None, 'sha1': None,
                'sha256': None, 'status': glare_fields.BlobFieldType.ACTIVE,
                'external': True, 'content_type': None}
        md5 = blob_meta.pop("md5", None)
        if md5 is None:
            msg = (_("Incorrect blob metadata %(meta)s. MD5 must be specified "
                     "for external location in artifact blob %(blob_name)."),
                   {"meta": str(blob_meta), "blob_name": blob_name})
            raise exception.BadRequest(msg)
        else:
            blob["md5"] = md5
            blob["sha1"] = blob_meta.pop("sha1", None)
            blob["sha256"] = blob_meta.pop("sha256", None)
        modified_af = cls.update_blob(
            context, type_name, artifact_id, blob, field_name, blob_key,
            validate=True)
        LOG.info(_LI("External location %(location)s has been created "
                     "successfully for artifact %(artifact)s blob %(blob)s"),
                 {'location': location, 'artifact': af.id,
                  'blob': blob_name})

        Notifier.notify(context, action_name, modified_af)
        return modified_af.to_dict()

    @classmethod
    def upload_blob(cls, context, type_name, artifact_id, field_name, fd,
                    content_type, blob_key=None):
        """Upload Artifact blob.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param field_name: name of blob or blob dict field
        :param fd: file descriptor that Glare uses to upload the file
        :param content_type: data content-type
        :param blob_key: if field_name is blob dict it specifies key
        in this dictionary
        :return: dict representation of updated artifact
        """
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = "artifact:upload"
        policy.authorize(action_name, af.to_dict(), context)

        try:
            # call upload hook
            lock_key = "%s:%s" % (type_name, artifact_id)
            with base.BaseArtifact.lock_engine.acquire(context, lock_key):
                fd, path = af.validate_upload(context, af, field_name, fd)
        except Exception as e:
            raise exception.BadRequest(message=str(e))

        try:
            # create an an empty blob instance in db with 'saving' status
            blob = {'url': None, 'size': None, 'md5': None, 'sha1': None,
                    'sha256': None,
                    'status': glare_fields.BlobFieldType.SAVING,
                    'external': False, 'content_type': content_type}
            modified_af = cls.update_blob(
                context, type_name, artifact_id, blob, field_name, blob_key,
                validate=True)

            if blob_key is None:
                blob_id = getattr(modified_af, field_name)['id']
            else:
                blob_id = getattr(modified_af, field_name)[blob_key]['id']

            # try to perform blob uploading to storage backend
            try:
                default_store = af.get_default_store(
                    context, af, field_name, blob_key)
                if default_store not in set(CONF.glance_store.stores):
                    LOG.warning(_LW('Incorrect backend configuration - scheme '
                                    '"%s" is not supported. Fallback to '
                                    'default store.'), default_store)
                    default_store = None
                location_uri, size, checksums = store_api.save_blob_to_store(
                    blob_id, fd, context, af.get_max_blob_size(field_name),
                    default_store)
            except Exception:
                # if upload failed remove blob from db and storage
                with excutils.save_and_reraise_exception(logger=LOG):
                    if blob_key is None:
                        af.update_blob(context, af.id, field_name, None)
                    else:
                        blob_dict_attr = modified_af[field_name]
                        del blob_dict_attr[blob_key]
                        af.update_blob(context, af.id,
                                       field_name, blob_dict_attr)
            blob_name = "%s[%s]" % (field_name, blob_key) \
                if blob_key else field_name
            LOG.info(_LI("Successfully finished blob upload for artifact "
                         "%(artifact)s blob field %(blob)s."),
                     {'artifact': af.id, 'blob': blob_name})

            # update blob info and activate it
            blob.update({'url': location_uri,
                         'status': glare_fields.BlobFieldType.ACTIVE,
                         'size': size})
            blob.update(checksums)
            modified_af = cls.update_blob(
                context, type_name, artifact_id, blob, field_name, blob_key)

            Notifier.notify(context, action_name, modified_af)
            return modified_af.to_dict()
        finally:
            if path:
                os.remove(path)

    @classmethod
    def update_blob(cls, context, type_name, artifact_id, blob,
                    field_name, blob_key=None, validate=False):
        """Update blob info.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param blob: blob representation in dict format
        :param field_name: name of blob or blob dict field
        :param blob_key: if field_name is blob dict it specifies key
        in this dict
        :param validate: enable validation of possibility of blob uploading

        :return: dict representation of updated artifact
        """
        lock_key = "%s:%s" % (type_name, artifact_id)
        with base.BaseArtifact.lock_engine.acquire(context, lock_key):
            af = cls._get_artifact(context, type_name, artifact_id)
            if validate:
                af.validate_upload_allowed(af, field_name, blob_key)
            if blob_key is None:
                setattr(af, field_name, blob)
                return af.update_blob(
                    context, af.id, field_name, getattr(af, field_name))
            else:
                blob_dict_attr = getattr(af, field_name)
                blob_dict_attr[blob_key] = blob
                return af.update_blob(
                    context, af.id, field_name, blob_dict_attr)

    @classmethod
    def download_blob(cls, context, type_name, artifact_id, field_name,
                      blob_key=None):
        """Download binary data from Glare Artifact.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param field_name: name of blob or blob dict field
        :param blob_key: if field_name is blob dict it specifies key
        in this dict
        :return: file iterator for requested file
        """
        af = cls._get_artifact(context, type_name, artifact_id,
                               read_only=True)
        policy.authorize("artifact:download", af.to_dict(), context)

        blob_name = "%s[%s]" % (field_name, blob_key)\
            if blob_key else field_name

        # check if property is downloadable
        if blob_key is None and not af.is_blob(field_name):
            msg = _("%s is not a blob") % field_name
            raise exception.BadRequest(msg)
        if blob_key is not None and not af.is_blob_dict(field_name):
            msg = _("%s is not a blob dict") % field_name
            raise exception.BadRequest(msg)

        if af.status == af.STATUS.DEACTIVATED and not context.is_admin:
            msg = _("Only admin is allowed to download artifact data "
                    "when it's deactivated")
            raise exception.Forbidden(message=msg)

        # get blob info from dict or directly
        if blob_key is None:
            blob = getattr(af, field_name)
        else:
            try:
                blob = getattr(af, field_name)[blob_key]
            except KeyError:
                msg = _("Blob with name %s is not found") % blob_name
                raise exception.NotFound(message=msg)

        if blob is None or blob['status'] != glare_fields.BlobFieldType.ACTIVE:
            msg = _("%s is not ready for download") % blob_name
            raise exception.BadRequest(message=msg)

        meta = {'md5': blob.get('md5'),
                'sha1': blob.get('sha1'),
                'sha256': blob.get('sha256'),
                'external': blob.get('external')}
        if blob['external']:
            data = {'url': blob['url']}
        else:
            data = store_api.load_from_store(uri=blob['url'], context=context)
            meta['size'] = blob.get('size')
            meta['content_type'] = blob.get('content_type')
        return data, meta
