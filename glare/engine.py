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

import jsonpatch
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import timeutils
from oslo_utils import uuidutils
import six.moves.urllib.parse as urlparse

from glare.common import exception
from glare.common import policy
from glare.common import store_api
from glare.common import utils
from glare.db import artifact_api
from glare.i18n import _
from glare import locking
from glare.notification import Notifier
from glare.objects.meta import registry
from glare import quota

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
     - pass data to base artifact type to execute all business logic operations
       with database;
     - check quotas during upload;
     - call operations pre- and post- hooks;
     - notify other users about finished operation.

    Engine should not include any business logic and validation related
    to artifacts types. Engine should not know any internal details of artifact
    type, because this part of the work is done by Base artifact type.
    """
    def __init__(self):
        # register all artifact types
        registry.ArtifactRegistry.register_all_artifacts()

        # generate all schemas and quotas
        self.schemas = {}
        self.config_quotas = {
            'max_artifact_number': CONF.max_artifact_number,
            'max_uploaded_data': CONF.max_uploaded_data
        }
        for name, type_list in registry.ArtifactRegistry.obj_classes().items():
            type_name = type_list[0].get_type_name()
            self.schemas[type_name] = registry.ArtifactRegistry.\
                get_artifact_type(type_name).gen_schemas()
            type_conf_section = getattr(CONF, 'artifact_type:' + type_name)
            if type_conf_section.max_artifact_number != -1:
                self.config_quotas['max_artifact_number:' + type_name] = \
                    type_conf_section.max_artifact_number
            if type_conf_section.max_uploaded_data != -1:
                self.config_quotas['max_uploaded_data:' + type_name] = \
                    type_conf_section.max_uploaded_data

    lock_engine = locking.LockEngine(artifact_api.ArtifactLockApi())

    def _create_scoped_lock(self, context, type_name, name, version,
                            owner, visibility='private'):
        """Create scoped lock for artifact."""
        # validate that artifact doesn't exist for the scope
        filters = [('name', 'eq:' + name), ('version', 'eq:' + version)]
        if visibility == 'public':
            filters.extend([('visibility', 'public')])
        elif visibility == 'private':
            filters.extend([('owner', 'eq:' + owner),
                            ('visibility', 'private')])

        scope_id = "%s:%s:%s" % (type_name, name, version)
        if visibility != 'public':
            scope_id += ':%s' % owner
        lock = self.lock_engine.acquire(context, scope_id)

        try:
            if self.list(context, type_name, filters).get("total_count") > 0:
                msg = _("Artifact with this name and version is already "
                        "exists for this scope.")
                raise exception.Conflict(msg)
        except Exception:
            with excutils.save_and_reraise_exception(logger=LOG):
                self.lock_engine.release(lock)

        return lock

    @staticmethod
    def _show_artifact(ctx, type_name, artifact_id,
                       read_only=False, get_any_artifact=False):
        """Return artifact requested by user.

        Check access permissions and policies.

        :param ctx: user context
        :param type_name: artifact type name
        :param artifact_id: id of the artifact to be updated
        :param read_only: flag, if set to True only read access is checked,
         if False then engine checks if artifact can be modified by the user
        :param get_any_artifact: flag, if set to True will get artifact from
        any realm
        """
        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        # only artifact is available for class users
        af = artifact_type.show(ctx, artifact_id, get_any_artifact)
        if not read_only and not get_any_artifact:
            if not ctx.is_admin and ctx.tenant != af.owner or ctx.read_only:
                raise exception.Forbidden()
            LOG.debug("Artifact %s acquired for read-write access",
                      artifact_id)
        else:
            LOG.debug("Artifact %s acquired for read-only access", artifact_id)

        return af

    def show_type_schemas(self, context, type_name=None):
        policy.authorize("artifact:type_list", {}, context)
        if type_name is None:
            return self.schemas
        if type_name not in self.schemas:
            msg = _("Artifact type %s does not exist") % type_name
            raise exception.NotFound(message=msg)
        return self.schemas[type_name]

    def _apply_patch(self, context, af, patch):
        # This function is a collection of hacks and workarounds to make
        # json patch apply changes to artifact object.
        action_names = ['update']
        af_dict = af.to_dict()
        policy.authorize('artifact:update', af_dict, context)
        af.pre_update_hook_with_patch(context, af, patch)
        try:
            for operation in patch._ops:
                # apply the change to make sure that it's correct
                af_dict = operation.apply(af_dict)

                # format of location is "/key/value" or just "/key"
                # first case symbolizes that we have dict or list insertion,
                # second, that we work with a field itself.
                items = operation.location.split('/', 2)
                field_name = items[1]
                if af.is_blob(field_name) or af.is_blob_dict(field_name):
                    msg = _("Cannot add blob with this request. "
                            "Use special Blob API for that.")
                    raise exception.BadRequest(msg)
                if len(items) == 2 and operation.operation['op'] == 'remove':
                    msg = _("Cannot remove field '%s' from "
                            "artifact.") % field_name
                    raise exception.BadRequest(msg)

                # work with hooks and define action names
                if field_name == 'visibility':
                    utils.validate_visibility_transition(
                        af,
                        from_visibility=af.visibility,
                        to_visibility=af_dict['visibility']
                    )
                    if af_dict['visibility'] == 'public':
                        policy.authorize(
                            'artifact:publish', af_dict, context)
                        af.pre_publish_hook(context, af)
                        action_names.append('publish')
                elif field_name == 'status':
                    utils.validate_status_transition(
                        af, from_status=af.status, to_status=af_dict['status'])
                    if af_dict['status'] == 'deactivated':
                        policy.authorize(
                            'artifact:deactivate', af_dict, context)
                        af.pre_deactivate_hook(context, af)
                        action_names.append('deactivate')
                    elif af_dict['status'] == 'active':
                        if af.status == 'deactivated':
                            policy.authorize(
                                'artifact:reactivate', af_dict, context)
                            af.pre_reactivate_hook(context, af)
                            action_names.append('reactivate')
                        else:
                            policy.authorize(
                                'artifact:activate', af_dict, context)
                            af.pre_activate_hook(context, af)
                            action_names.append('activate')
                else:
                    utils.validate_change_allowed(af, field_name)

                old_val = getattr(af, field_name)
                setattr(af, field_name, af_dict[field_name])
                if operation.operation.get("op") == "move":
                    source_field = operation.from_path
                    setattr(af, source_field, af_dict[source_field])
                new_val = getattr(af, field_name)
                if new_val == old_val:
                    # No need to save value to db if it's not changed
                    af.obj_reset_changes([field_name])

        except (jsonpatch.JsonPatchException,
                jsonpatch.JsonPointerException, TypeError) as e:
            raise exception.BadRequest(message=str(e))

        return action_names

    def create(self, context, type_name, values):
        """Create artifact record in Glare.

        :param context: user context
        :param type_name: artifact type name
        :param values: dict with artifact fields
        :return: dict representation of created artifact
        """
        action_name = "artifact:create"
        policy.authorize(action_name, values, context)
        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        version = values.get('version', artifact_type.DEFAULT_ARTIFACT_VERSION)
        init_values = {
            'id': uuidutils.generate_uuid(),
            'name': values.pop('name'),
            'version': version,
            'owner': context.project_id,
            'created_at': timeutils.utcnow(),
            'updated_at': timeutils.utcnow()
        }
        for k, v in values.items():
            init_values[k] = v

        af = artifact_type.init_artifact(context, init_values)
        # acquire scoped lock and execute artifact create
        with self._create_scoped_lock(context, type_name, af.name,
                                      af.version, context.project_id):
            quota.verify_artifact_count(context, type_name)
            for field_name, value in values.items():
                if af.is_blob(field_name) or af.is_blob_dict(field_name):
                    msg = _("Cannot add blob with this request. "
                            "Use special Blob API for that.")
                    raise exception.BadRequest(msg)
                utils.validate_change_allowed(af, field_name)
                setattr(af, field_name, value)
            artifact_type.pre_create_hook(context, af)
            af = af.create(context)
            artifact_type.post_create_hook(context, af)
            # notify about new artifact
            Notifier.notify(context, action_name, af)
            # return artifact to the user
            return af.to_dict()

    def save(self, context, type_name, artifact_id, patch):
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
        lock_key = "%s:%s" % (type_name, artifact_id)
        with self.lock_engine.acquire(context, lock_key):
            af = self._show_artifact(context, type_name, artifact_id)
            af.obj_reset_changes()
            action_names = self._apply_patch(context, af, patch)
            updates = af.obj_changes_to_primitive()

            LOG.debug("Update diff successfully calculated for artifact "
                      "%(af)s %(diff)s", {'af': artifact_id, 'diff': updates})
            if not updates:
                return af.to_dict()

            if any(i in updates for i in ('name', 'version', 'visibility')):
                # to change an artifact scope it's required to set a lock first
                with self._create_scoped_lock(
                        context, type_name, updates.get('name', af.name),
                        updates.get('version', af.version), af.owner,
                        updates.get('visibility', af.visibility)):
                    af = af.save(context)
            else:
                af = af.save(context)

            # call post hooks for all operations when data is written in db and
            # send broadcast notifications
            for action_name in action_names:
                getattr(af, 'post_%s_hook' % action_name)(context, af)
                Notifier.notify(context, 'artifact:' + action_name, af)

            return af.to_dict()

    def show(self, context, type_name, artifact_id):
        """Show detailed artifact info.

        :param context: user context
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to show
        :return: definition of requested artifact
        """
        get_any_artifact = False
        if policy.authorize("artifact:get_any_artifact", {},
                            context, do_raise=False):
            get_any_artifact = True
        policy.authorize("artifact:get", {}, context)
        af = self._show_artifact(context, type_name, artifact_id,
                                 read_only=True,
                                 get_any_artifact=get_any_artifact)
        return af.to_dict()

    @staticmethod
    def list(context, type_name, filters, marker=None, limit=None,
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
        list_all_artifacts = False
        if policy.authorize("artifact:list_all_artifacts",
                            {}, context, do_raise=False):
            list_all_artifacts = True
        policy.authorize("artifact:list", {}, context)
        artifact_type = registry.ArtifactRegistry.get_artifact_type(type_name)
        # return list to the user

        artifacts_data = artifact_type.list(
            context, filters, marker, limit, sort, latest, list_all_artifacts)
        artifacts_data["artifacts"] = [af.to_dict()
                                       for af in artifacts_data["artifacts"]]
        return artifacts_data

    @staticmethod
    def _delete_blobs(context, af, blobs):
        for name, blob in blobs.items():
            if af.is_blob(name):
                if not blob['external']:
                    try:
                        store_api.delete_blob(blob['url'], context=context)
                    except exception.NotFound:
                        # data has already been removed
                        pass
                af.db_api.update_blob(context, af.id, {name: None})
            elif af.is_blob_dict(name):
                upd_blob = deepcopy(blob)
                for key, val in blob.items():
                    if not val['external']:
                        try:
                            store_api.delete_blob(val['url'], context=context)
                        except exception.NotFound:
                            pass
                    del upd_blob[key]
                    af.db_api.update_blob(context, af.id, {name: upd_blob})

    def delete(self, context, type_name, artifact_id):
        """Delete artifact from Glare.

        :param context: User context
        :param type_name: Artifact type name
        :param artifact_id: id of artifact to delete
        """
        af = self._show_artifact(context, type_name, artifact_id)
        action_name = 'artifact:delete'
        policy.authorize(action_name, af.to_dict(), context)
        af.pre_delete_hook(context, af)
        blobs = af.delete(context, af)

        delayed_delete = getattr(
            CONF, 'artifact_type:' + type_name).delayed_delete
        # use global parameter if delayed delete isn't set per artifact type
        if delayed_delete is None:
            delayed_delete = CONF.delayed_delete

        if not delayed_delete:
            if blobs:
                # delete blobs one by one
                self._delete_blobs(context, af, blobs)
                LOG.info("Blobs successfully deleted for artifact %s", af.id)
            # delete artifact itself
            af.db_api.delete(context, af.id)
        af.post_delete_hook(context, af)
        Notifier.notify(context, action_name, af)

    @staticmethod
    def _get_blob_info(af, field_name, blob_key=None):
        """Return requested blob info."""
        if blob_key:
            if not af.is_blob_dict(field_name):
                msg = _("%s is not a blob dict") % field_name
                raise exception.BadRequest(msg)
            return getattr(af, field_name).get(blob_key)
        else:
            if not af.is_blob(field_name):
                msg = _("%s is not a blob") % field_name
                raise exception.BadRequest(msg)
            return getattr(af, field_name, None)

    @staticmethod
    def _save_blob_info(context, af, field_name, blob_key, value):
        """Save blob instance in database."""
        if blob_key is not None:
            # Insert blob value in the folder
            folder = getattr(af, field_name)
            if value is not None:
                folder[blob_key] = value
            else:
                del folder[blob_key]
            value = folder
        return af.update_blob(context, af.id, field_name, value)

    @staticmethod
    def _generate_blob_name(field_name, blob_key=None):
        return "%s[%s]" % (field_name, blob_key) if blob_key else field_name

    def add_blob_location(self, context, type_name, artifact_id, field_name,
                          location, blob_meta, blob_key=None):
        """Add external/internal location to blob.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param field_name: name of blob or blob dict field
        :param location: blob url
        :param blob_meta: dictionary containing blob metadata like md5 checksum
        :param blob_key: if field_name is blob dict it specifies key
         in this dict
        :return: dict representation of updated artifact
        """
        blob_name = self._generate_blob_name(field_name, blob_key)

        location_type = blob_meta.pop('location_type', 'external')

        if location_type == 'external':
            action_name = 'artifact:set_location'
        elif location_type == 'internal':
            scheme = urlparse.urlparse(location).scheme
            if scheme in store_api.RESTRICTED_URI_SCHEMES:
                msg = _("Forbidden to set internal locations with "
                        "scheme '%s'") % scheme
                raise exception.Forbidden(msg)
            if scheme not in store_api.get_known_schemes():
                msg = _("Unknown scheme '%s'") % scheme
                raise exception.BadRequest(msg)
            action_name = 'artifact:set_internal_location'
        else:
            msg = _("Invalid location type: %s") % location_type
            raise exception.BadRequest(msg)

        blob = {'url': location, 'size': None, 'md5': blob_meta.get("md5"),
                'sha1': blob_meta.get("sha1"), 'id': uuidutils.generate_uuid(),
                'sha256': blob_meta.get("sha256"), 'status': 'active',
                'external': location_type == 'external', 'content_type': None}

        lock_key = "%s:%s" % (type_name, artifact_id)
        with self.lock_engine.acquire(context, lock_key):
            af = self._show_artifact(context, type_name, artifact_id)
            policy.authorize(action_name, af.to_dict(), context)
            if self._get_blob_info(af, field_name, blob_key):
                msg = _("Blob %(blob)s already exists for artifact "
                        "%(af)s") % {'blob': field_name, 'af': af.id}
                raise exception.Conflict(message=msg)
            utils.validate_change_allowed(af, field_name)
            af.pre_add_location_hook(
                context, af, field_name, location, blob_key)
            af = self._save_blob_info(context, af, field_name, blob_key, blob)

        LOG.info("External location %(location)s has been created "
                 "successfully for artifact %(artifact)s blob %(blob)s",
                 {'location': location, 'artifact': af.id,
                  'blob': blob_name})

        af.post_add_location_hook(context, af, field_name, blob_key)
        Notifier.notify(context, action_name, af)
        return af.to_dict()

    def _calculate_allowed_space(self, context, af, field_name,
                                 content_length=None, blob_key=None):
        """Calculate the maximum amount of data user can upload to the blob."""
        # As a default we take the maximum blob size
        blob_name = self._generate_blob_name(field_name, blob_key)

        max_blob_size = af.get_max_blob_size(field_name)

        if blob_key is not None:
            # For folders we also compare it with the maximum folder size
            blobs_dict = getattr(af, field_name)
            overall_folder_size = sum(
                blob["size"] for blob in blobs_dict.values()
                if blob["size"] is not None)
            available_folder_space = af.get_max_folder_size(
                field_name) - overall_folder_size  # always non-negative
            max_blob_size = min(max_blob_size, available_folder_space)

        # check quotas
        quota_size = quota.verify_uploaded_data_amount(
            context, af.get_type_name(), content_length)

        if content_length is None:
            # if no content_length was provided we have to allocate
            # all allowed space for the blob. It's minimum of max blob size
            # and available quota limit. -1 means that user don't have upload
            # limits.
            size = max_blob_size if quota_size == -1 else min(
                max_blob_size, quota_size)
        else:
            if content_length > max_blob_size:
                msg = _("Can't upload %(content_length)d bytes of data to "
                        "blob %(blob_name)s. Its max allowed size is "
                        "%(max_blob_size)d") % {
                    'content_length': content_length,
                    'blob_name': blob_name,
                    'max_blob_size': max_blob_size}
                raise exception.RequestEntityTooLarge(msg)
            size = content_length

        return size

    def upload_blob(self, context, type_name, artifact_id, field_name, fd,
                    content_type, content_length=None, blob_key=None):
        """Upload Artifact blob.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param field_name: name of blob or blob dict field
        :param fd: file descriptor that Glare uses to upload the file
        :param content_type: data content-type
        :param content_length: amount of data user wants to upload
        :param blob_key: if field_name is blob dict it specifies key
         in this dictionary
        :return: dict representation of updated artifact
        """
        blob_name = self._generate_blob_name(field_name, blob_key)
        blob_id = uuidutils.generate_uuid()
        blob_info = {'url': None, 'size': None, 'md5': None, 'sha1': None,
                     'sha256': None, 'id': blob_id, 'status': 'saving',
                     'external': False, 'content_type': content_type}

        # Step 1. Initialize blob
        lock_key = "%s:%s" % (type_name, artifact_id)
        with self.lock_engine.acquire(context, lock_key):
            af = self._show_artifact(context, type_name, artifact_id)
            action_name = "artifact:upload"
            policy.authorize(action_name, af.to_dict(), context)

            # create an an empty blob instance in db with 'saving' status
            existing_blob = self._get_blob_info(af, field_name, blob_key)
            existing_blob_status = existing_blob.get("status")\
                if existing_blob else None
            if existing_blob_status == "saving":
                msg = _("Blob %(blob)s already exists for artifact and it"
                        "is in %(status)s %(af)s") % {
                    'blob': field_name, 'af': af.id,
                    'status': existing_blob_status}
                raise exception.Conflict(message=msg)
            utils.validate_change_allowed(af, field_name)

            if existing_blob is not None:
                blob_info = deepcopy(existing_blob)
                blob_info['status'] = 'saving'

            blob_info['size'] = self._calculate_allowed_space(
                context, af, field_name, content_length, blob_key)

            af = self._save_blob_info(
                context, af, field_name, blob_key, blob_info)

        LOG.debug("Parameters validation for artifact %(artifact)s blob "
                  "upload passed for blob %(blob_name)s. "
                  "Start blob uploading to backend.",
                  {'artifact': af.id, 'blob_name': blob_name})

        # Step 2. Call pre_upload_hook and upload data to the store
        try:
            try:
                # call upload hook first
                if hasattr(af, 'validate_upload'):
                    LOG.warning("Method 'validate_upload' was deprecated. "
                                "Please use 'pre_upload_hook' instead.")
                    fd, path = af.validate_upload(context, af, field_name, fd)
                else:
                    LOG.debug("Initiating Pre_upload hook")
                    fd = af.pre_upload_hook(context, af, field_name,
                                            blob_key, fd)
                    LOG.debug("Pre_upload hook executed successfully")
            except exception.GlareException:
                raise
            except Exception as e:
                raise exception.BadRequest(message=str(e))

            default_store = getattr(
                CONF, 'artifact_type:' + type_name).default_store
            # use global parameter if default store isn't set per artifact type
            if default_store is None:
                default_store = CONF.glance_store.default_store

            location_uri, size, checksums = store_api.save_blob_to_store(
                blob_id, fd, context, blob_info['size'],
                store_type=default_store)
            blob_info.update({'url': location_uri,
                              'status': 'active',
                              'size': size})
            blob_info.update(checksums)
        except Exception:
            # if upload failed remove blob from db and storage
            with excutils.save_and_reraise_exception(logger=LOG):
                LOG.error("Exception occured: %s", Exception)
                # delete created blob_info in case of blob_data upload fails.
                if existing_blob is None:
                    blob_info = None
                else:
                    # Update size of blob_data to previous blob and
                    # Mark existing blob status to active.
                    blob_info['size'] = existing_blob['size']
                    blob_info['status'] = 'active'
                self._save_blob_info(
                    context, af, field_name, blob_key, blob_info)

        LOG.info("Successfully finished blob uploading for artifact "
                 "%(artifact)s blob field %(blob)s.",
                 {'artifact': af.id, 'blob': blob_name})

        # Step 3. Change blob status to 'active'
        try:
            with self.lock_engine.acquire(context, lock_key):
                af = af.show(context, artifact_id)
                af = self._save_blob_info(
                    context, af, field_name, blob_key, blob_info)
        except Exception as e:
            msg = _("Exception occured while updating blob status to active"
                    " for artifact Id : [%(artifact_id)s] , %(error_msg)s") %\
                {"artifact_id": artifact_id, "error_msg": str(e)}
            LOG.error(msg)
            raise

        af.post_upload_hook(context, af, field_name, blob_key)

        Notifier.notify(context, action_name, af)
        return af.to_dict()

    def download_blob(self, context, type_name, artifact_id, field_name,
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
        download_from_any_artifact = False
        if policy.authorize("artifact:download_from_any_artifact", {},
                            context, do_raise=False):
            download_from_any_artifact = True

        af = self._show_artifact(context, type_name, artifact_id,
                                 read_only=True,
                                 get_any_artifact=download_from_any_artifact)

        if not download_from_any_artifact:
            policy.authorize("artifact:download", af.to_dict(), context)

        blob_name = self._generate_blob_name(field_name, blob_key)

        if af.status == 'deleted':
            msg = _("Cannot download data when artifact is deleted")
            raise exception.Forbidden(message=msg)

        blob = self._get_blob_info(af, field_name, blob_key)
        if blob is None:
            msg = _("No data found for blob %s") % blob_name
            raise exception.NotFound(message=msg)
        if blob['status'] != 'active':
            msg = _("%s is not ready for download") % blob_name
            raise exception.Conflict(message=msg)

        af.pre_download_hook(context, af, field_name, blob_key)

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

        try:
            # call download hook in the end
            data = af.post_download_hook(
                context, af, field_name, blob_key, data)
        except exception.GlareException:
            raise
        except Exception as e:
            raise exception.BadRequest(message=str(e))

        return data, meta

    def delete_external_blob(self, context, type_name, artifact_id,
                             field_name, blob_key=None):
        """Delete artifact blob with external location.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of artifact with the blob to delete
        :param field_name: name of blob or blob dict field
        :param blob_key: if field_name is blob dict it specifies key
         in this dictionary
        """
        af = self._show_artifact(context, type_name, artifact_id)
        action_name = 'artifact:delete_blob'
        policy.authorize(action_name, af.to_dict(), context)

        blob_name = self._generate_blob_name(field_name, blob_key)

        blob = self._get_blob_info(af, field_name, blob_key)
        if blob is None:
            msg = _("Blob %s wasn't found for artifact") % blob_name
            raise exception.NotFound(message=msg)
        if not blob['external']:
            msg = _("Blob %s is not external") % blob_name
            raise exception.Forbidden(message=msg)

        af = self._save_blob_info(context, af, field_name, blob_key, None)

        Notifier.notify(context, action_name, af)
        return af.to_dict()

    @staticmethod
    def set_quotas(context, values):
        """Set quota records in Glare.

        :param context: user request context
        :param values: dict with quota values to set
        """
        action_name = "artifact:set_quotas"
        policy.authorize(action_name, {}, context)
        qs = quota.set_quotas(values)
        Notifier.notify(context, action_name, qs)

    def list_all_quotas(self, context):
        """Get detailed info about all available quotas.

        :param context: user request context
        :return: dict with definitions of redefined quotas for all projects
         and global defaults
        """
        action_name = "artifact:list_all_quotas"
        policy.authorize(action_name, {}, context)
        return {
            'quotas': quota.list_quotas(),
            'global_quotas': self.config_quotas
        }

    def list_project_quotas(self, context, project_id=None):
        """Get detailed info about project quotas.

        :param context: user request context
        :param project_id: id of the project for which to show quotas
        :return: definition of requested quotas for the project
        """
        project_id = project_id or context.project_id
        action_name = "artifact:list_project_quotas"
        policy.authorize(action_name, {'project_id': project_id}, context)
        qs = self.config_quotas.copy()
        qs.update(quota.list_quotas(project_id)[project_id])
        return {project_id: qs}
