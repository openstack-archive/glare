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

import jsonpatch
from oslo_log import log as logging

from glare.common import exception
from glare.common import policy
from glare.common import utils
from glare.db import artifact_api
from glare.i18n import _
from glare import locking
from glare.notification import Notifier
from glare.objects.meta import registry as glare_registry

LOG = logging.getLogger(__name__)


class Engine(object):
    """Engine is responsible for executing different helper operations when
    processing incoming requests from Glare API.
    Engine receives incoming data and does the following:
    - check basic policy permissions
    - requests artifact definition from registry
    - check access permission(ro, rw)
    - lock artifact for update if needed
    - pass data to base artifact to execute all business logic operations
    - notify other users about finished operation.
    Engine should not include any business logic and validation related
    to Artifacts. Engine should not know any internal details of Artifacts
    because it controls access to Artifacts in common.
    """

    registry = glare_registry.ArtifactRegistry
    registry.register_all_artifacts()
    lock_engine = locking.LockEngine(artifact_api.ArtifactLockApi())

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
        """Return artifact for users

        Return artifact for reading/modification by users. Check
        access permissions and policies for artifact.
        """

        def _check_read_write_access(ctx, af):
            """Check if artifact can be modified by user

            :param ctx: user context
            :param af: artifact definition
            :raise Forbidden if access is not allowed
            """
            if not ctx.is_admin and ctx.tenant != af.owner or ctx.read_only:
                raise exception.Forbidden()

        def _check_read_only_access(ctx, af):
            """Check if user has read only access to artifact

            :param ctx: user context
            :param af: artifact definition
            :raise Forbidden if access is not allowed
            """
            private = af.visibility != 'public'
            if (private and
                    not ctx.is_admin and ctx.tenant != af.owner):
                # TODO(kairat): check artifact sharing here
                raise exception.Forbidden()

        artifact_type = Engine.registry.get_artifact_type(type_name)
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
        return cls._get_schemas(cls.registry)

    @classmethod
    def show_type_schema(cls, context, type_name):
        policy.authorize("artifact:type_list", {}, context)
        schemas = cls._get_schemas(cls.registry)
        if type_name not in schemas:
            msg = _("Artifact type %s does not exist") % type_name
            raise exception.NotFound(message=msg)
        return schemas[type_name]

    @classmethod
    def create(cls, context, type_name, field_values):
        """Create new artifact in Glare"""
        action_name = "artifact:create"
        policy.authorize(action_name, field_values, context)
        artifact_type = cls.registry.get_artifact_type(type_name)
        # acquire version lock and execute artifact create
        af = artifact_type.create(context, field_values)
        # notify about new artifact
        Notifier.notify(context, action_name, af)
        # return artifact to the user
        return af.to_dict()

    @classmethod
    @lock_engine.locked(['type_name', 'artifact_id'])
    def update(cls, context, type_name, artifact_id, patch):
        """Update artifact with json patch.

        Apply patch to artifact and validate artifact before updating it
        in database. If there is request for visibility change or custom
        location change then call specific method for that.

        :param context: user context
        :param type_name: name of artifact type
        :param artifact_id: id of the artifact to be updated
        :param patch: json patch
        :return: updated artifact
        """

        def get_updates(af_dict, patch_with_upd):
            """Get updated values for artifact and json patch

            :param af_dict: current artifact definition as dict
            :param patch_with_upd: json-patch
            :return: dict of updated attributes and their values
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

        artifact = cls._get_artifact(context, type_name, artifact_id)
        af_dict = artifact.to_dict()
        updates = get_updates(af_dict, patch)
        LOG.debug("Update diff successfully calculated for artifact %(af)s "
                  "%(diff)s", {'af': artifact_id, 'diff': updates})

        if not updates:
            return af_dict
        else:
            action = artifact.get_action_for_updates(context, artifact,
                                                     updates, cls.registry)
            action_name = "artifact:%s" % action.__name__
            policy.authorize(action_name, af_dict, context)
            modified_af = action(context, artifact, updates)
            Notifier.notify(context, action_name, modified_af)
            return modified_af.to_dict()

    @classmethod
    def get(cls, context, type_name, artifact_id):
        """Return artifact representation from artifact repo."""
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
        :return: list of artifacts
        """
        policy.authorize("artifact:list", {}, context)
        artifact_type = cls.registry.get_artifact_type(type_name)
        # return list to the user
        af_list = [af.to_dict()
                   for af in artifact_type.list(context, filters, marker,
                                                limit, sort, latest)]
        return af_list

    @classmethod
    def delete(cls, context, type_name, artifact_id):
        """Delete artifact from glare"""
        af = cls._get_artifact(context, type_name, artifact_id)
        policy.authorize("artifact:delete", af.to_dict(), context)
        af.delete(context, af)
        Notifier.notify(context, "artifact.delete", af)

    @classmethod
    @lock_engine.locked(['type_name', 'artifact_id'])
    def add_blob_location(cls, context, type_name,
                          artifact_id, field_name, location, blob_meta):
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = 'artifact:set_location'
        policy.authorize(action_name, af.to_dict(), context)
        modified_af = af.add_blob_location(context, af, field_name, location,
                                           blob_meta)
        Notifier.notify(context, action_name, modified_af)
        return modified_af.to_dict()

    @classmethod
    @lock_engine.locked(['type_name', 'artifact_id'])
    def add_blob_dict_location(cls, context, type_name, artifact_id,
                               field_name, blob_key, location, blob_meta):
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = 'artifact:set_location'
        policy.authorize(action_name, af.to_dict(), context)
        modified_af = af.add_blob_dict_location(context, af, field_name,
                                                blob_key, location, blob_meta)
        Notifier.notify(context, action_name, modified_af)
        return modified_af.to_dict()

    @classmethod
    @lock_engine.locked(['type_name', 'artifact_id'])
    def upload_blob(cls, context, type_name, artifact_id, field_name, fd,
                    content_type):
        """Upload Artifact blob"""
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = "artifact:upload"
        policy.authorize(action_name, af.to_dict(), context)
        modified_af = af.upload_blob(context, af, field_name, fd, content_type)
        Notifier.notify(context, action_name, modified_af)
        return modified_af.to_dict()

    @classmethod
    @lock_engine.locked(['type_name', 'artifact_id'])
    def upload_blob_dict(cls, context, type_name, artifact_id, field_name,
                         blob_key, fd, content_type):
        """Upload Artifact blob to dict"""
        af = cls._get_artifact(context, type_name, artifact_id)
        action_name = "artifact:upload"
        policy.authorize(action_name, af.to_dict(), context)
        modified_af = af.upload_blob_dict(context, af, field_name, blob_key,
                                          fd, content_type)
        Notifier.notify(context, action_name, modified_af)
        return modified_af.to_dict()

    @classmethod
    def download_blob(cls, context, type_name, artifact_id, field_name):
        """Download blob from artifact"""
        af = cls._get_artifact(context, type_name, artifact_id,
                               read_only=True)
        policy.authorize("artifact:download", af.to_dict(), context)
        return af.download_blob(context, af, field_name)

    @classmethod
    def download_blob_dict(cls, context, type_name, artifact_id, field_name,
                           blob_key):
        """Download blob from artifact"""
        af = cls._get_artifact(context, type_name, artifact_id,
                               read_only=True)
        policy.authorize("artifact:download", af.to_dict(), context)
        return af.download_blob_dict(context, af, field_name, blob_key)
