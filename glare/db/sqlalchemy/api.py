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

import operator
import threading
import uuid

from oslo_config import cfg
from oslo_db import exception as db_exception
from oslo_db.sqlalchemy import session
from oslo_log import log as os_logging
from oslo_utils import timeutils
import osprofiler.sqlalchemy
from retrying import retry
import six
import sqlalchemy
from sqlalchemy import and_
import sqlalchemy.exc
from sqlalchemy import func
from sqlalchemy import or_
import sqlalchemy.orm as orm
from sqlalchemy.orm import aliased
from sqlalchemy.orm import joinedload

from glare.common import exception
from glare.common import semver_db
from glare.common import utils
from glare.db.sqlalchemy import models
from glare.i18n import _, _LW

LOG = os_logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group("profiler", "glare.common.wsgi")


BASE_ARTIFACT_PROPERTIES = ('id', 'visibility', 'created_at', 'updated_at',
                            'activated_at', 'owner', 'status', 'description',
                            'name', 'type_name', 'version')

DEFAULT_SORT_PARAMETERS = (('created_at', 'desc', None), ('id', 'asc', None))

_FACADE = None
_LOCK = threading.Lock()


def _retry_on_deadlock(exc):
    """Decorator to retry a DB API call if Deadlock was received."""

    if isinstance(exc, db_exception.DBDeadlock):
        LOG.warn(_LW("Deadlock detected. Retrying..."))
        return True
    return False


def _create_facade_lazily():
    global _LOCK, _FACADE
    if _FACADE is None:
        with _LOCK:
            if _FACADE is None:
                _FACADE = session.EngineFacade.from_config(CONF)

                if CONF.profiler.enabled and CONF.profiler.trace_sqlalchemy:
                    osprofiler.sqlalchemy.add_tracing(sqlalchemy,
                                                      _FACADE.get_engine(),
                                                      "db")
    return _FACADE


def get_engine():
    facade = _create_facade_lazily()
    return facade.get_engine()


def get_session(autocommit=True, expire_on_commit=False):
    facade = _create_facade_lazily()
    return facade.get_session(autocommit=autocommit,
                              expire_on_commit=expire_on_commit)


def clear_db_env():
    """
    Unset global configuration variables for database.
    """
    global _FACADE
    _FACADE = None


def create(context, values, session):
    return _create_or_update(context, None, values, session)


def update(context, artifact_id, values, session):
    return _create_or_update(context, artifact_id, values, session)


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def delete(context, artifact_id, session):
    artifact = _get(context, artifact_id, session)
    artifact.properties = []
    artifact.tags = []
    artifact.status = 'deleted'
    artifact.save(session=session)


def _drop_protected_attrs(model_class, values):
    """
    Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def _create_or_update(context, artifact_id, values, session):
    with session.begin():
        _drop_protected_attrs(models.Artifact, values)
        if artifact_id is None:
            if 'type_name' not in values:
                msg = _('Type name must be set.')
                raise exception.BadRequest(msg)
            # create new artifact
            artifact = models.Artifact()
            if 'id' not in values:
                artifact.id = str(uuid.uuid4())
            else:
                artifact.id = values.pop('id')
            artifact.created_at = timeutils.utcnow()
        else:
            # update the existing artifact
            artifact = _get(context, artifact_id, session)

        if 'version' in values:
            values['version'] = semver_db.parse(values['version'])

        if 'tags' in values:
            tags = values.pop('tags')
            artifact.tags = _do_tags(artifact, tags)

        if 'properties' in values:
            properties = values.pop('properties', {})
            artifact.properties = _do_properties(artifact, properties)

        if 'blobs' in values:
            blobs = values.pop('blobs')
            artifact.blobs = _do_blobs(artifact, blobs)

        artifact.updated_at = timeutils.utcnow()
        if 'status' in values and values['status'] == 'active':
            artifact.activated_at = timeutils.utcnow()
        artifact.update(values)
        artifact.save(session=session)

        return artifact.to_dict()


def _get(context, artifact_id, session):
    try:
        query = _do_artifacts_query(context, session).filter_by(
            id=artifact_id)
        artifact = query.one()
    except orm.exc.NoResultFound:
        msg = _("Artifact with id=%s not found.") % artifact_id
        LOG.warn(msg)
        raise exception.ArtifactNotFound(msg)
    return artifact


def get(context, artifact_id, session):
    return _get(context, artifact_id, session).to_dict()


def get_all(context, session, filters=None, marker=None, limit=None,
            sort=None, latest=False):
    """List all visible artifacts
    :param filters: dict of filter keys and values.
    :param marker: artifact id after which to start page
    :param limit: maximum number of artifacts to return
    :param sort: a tuple (key, dir, type) where key is an attribute by
    which results should be sorted, dir is a direction: 'asc' or 'desc',
    and type is type of the attribute: 'bool', 'string', 'numeric' or 'int' or
    None if attribute is base.
    :param latest: flag that indicates, that only artifacts with highest
    versions should be returned in output
    """
    artifacts = _get_all(
        context, session, filters, marker, limit, sort, latest)
    return [af.to_dict() for af in artifacts]


def _apply_latest_filter(context, session, query,
                         basic_conds, tag_conds, prop_conds):
    # Subquery to fetch max version suffix for a group (name,
    # version_prefix)
    ver_suffix_subq = _apply_query_base_filters(
        session.query(
            models.Artifact.name,
            models.Artifact.version_prefix,
            func.max(models.Artifact.version_suffix).label(
                'max_suffix')).group_by(
            models.Artifact.name, models.Artifact.version_prefix),
        context)
    ver_suffix_subq = _apply_user_filters(
        ver_suffix_subq, basic_conds, tag_conds, prop_conds).subquery()
    # Subquery to fetch max version prefix for a name group
    ver_prefix_subq = _apply_query_base_filters(
        session.query(models.Artifact.name, func.max(
            models.Artifact.version_prefix).label('max_prefix')).group_by(
            models.Artifact.name),
        context)
    ver_prefix_subq = _apply_user_filters(
        ver_prefix_subq, basic_conds, tag_conds, prop_conds).subquery()
    # Combine two subqueries together joining them with Artifact table
    query = query.join(
        ver_prefix_subq,
        and_(models.Artifact.name == ver_prefix_subq.c.name,
             models.Artifact.version_prefix ==
             ver_prefix_subq.c.max_prefix)).join(
        ver_suffix_subq,
        and_(models.Artifact.name == ver_suffix_subq.c.name,
             models.Artifact.version_prefix ==
             ver_suffix_subq.c.version_prefix,
             models.Artifact.version_suffix ==
             ver_suffix_subq.c.max_suffix)
    )

    return query


def _apply_user_filters(query, basic_conds, tag_conds, prop_conds):

    if basic_conds:
        for basic_condition in basic_conds:
            query = query.filter(and_(*basic_condition))

    if tag_conds:
        for tag_condition in tag_conds:
            query = query.join(models.ArtifactTag, aliased=True).filter(
                and_(*tag_condition))

    if prop_conds:
        for prop_condition in prop_conds:
            query = query.join(models.ArtifactProperty, aliased=True).filter(
                and_(*prop_condition))

    return query


def _get_all(context, session, filters=None, marker=None, limit=None,
             sort=None, latest=False):

    filters = filters or {}

    query = _do_artifacts_query(context, session)

    basic_conds, tag_conds, prop_conds = _do_query_filters(filters)

    query = _apply_user_filters(query, basic_conds, tag_conds, prop_conds)

    if latest:
        query = _apply_latest_filter(context, session, query,
                                     basic_conds, tag_conds, prop_conds)

    marker_artifact = None
    if marker is not None:
        marker_artifact = get(context, marker, session)

    if sort is None:
        sort = DEFAULT_SORT_PARAMETERS
    else:
        for val in DEFAULT_SORT_PARAMETERS:
            if val not in sort:
                sort.append(val)

    query = _do_paginate_query(query=query, limit=limit,
                               marker=marker_artifact, sort=sort)

    return query.all()


def _do_paginate_query(query, marker=None, limit=None, sort=None):
    # Add sorting
    number_of_custom_props = 0
    for sort_key, sort_dir, sort_type in sort:
        try:
            sort_dir_func = {
                'asc': sqlalchemy.asc,
                'desc': sqlalchemy.desc,
            }[sort_dir]
        except KeyError:
            msg = _("Unknown sort direction, must be 'desc' or 'asc'.")
            raise exception.BadRequest(msg)
        # Note(mfedosin): Workaround to deal with situation that sqlalchemy
        # cannot work with composite keys correctly
        if sort_key == 'version':
            query = query.order_by(sort_dir_func(models.Artifact.version_prefix))\
                         .order_by(sort_dir_func(models.Artifact.version_suffix))\
                         .order_by(sort_dir_func(models.Artifact.version_meta))
        elif sort_key in BASE_ARTIFACT_PROPERTIES:
            # sort by generic property
            query = query.order_by(sort_dir_func(getattr(models.Artifact,
                                                         sort_key)))
        else:
            # sort by custom property
            number_of_custom_props += 1
            if number_of_custom_props > 1:
                msg = _("For performance sake it's not allowed to sort by "
                        "more than one custom property with this db backend.")
                raise exception.BadRequest(msg)
            prop_table = aliased(models.ArtifactProperty)
            query = (
                query.join(prop_table).
                filter(prop_table.name == sort_key).
                order_by(sort_dir_func(getattr(prop_table,
                                               sort_type + '_value'))))

    # Add pagination
    if marker is not None:
        marker_values = []
        for sort_key, __, __ in sort:
            v = marker.get(sort_key, None)
            marker_values.append(v)

        # Build up an array of sort criteria as in the docstring
        criteria_list = []
        for i in range(len(sort)):
            crit_attrs = []
            for j in range(i):
                value = marker_values[j]
                if sort[j][0] in BASE_ARTIFACT_PROPERTIES:
                    if sort[j][0] == 'version':
                        value = semver_db.parse(value)
                    crit_attrs.append([getattr(models.Artifact, sort[j][0]) ==
                                       value])
                else:
                    conds = [models.ArtifactProperty.name == sort[j][0]]
                    conds.extend([getattr(models.ArtifactProperty,
                                 sort[j][2] + '_value') == value])
                    crit_attrs.append(conds)

            value = marker_values[i]
            sort_dir_func = operator.gt if sort[i][1] == 'asc' else operator.lt
            if sort[i][0] in BASE_ARTIFACT_PROPERTIES:
                if sort[i][0] == 'version':
                    value = semver_db.parse(value)
                crit_attrs.append([sort_dir_func(getattr(models.Artifact,
                                                         sort[i][0]), value)])
            else:
                query = query.join(models.ArtifactProperty, aliased=True)
                conds = [models.ArtifactProperty.name == sort[i][0]]
                conds.extend([sort_dir_func(getattr(models.ArtifactProperty,
                             sort[i][2] + '_value'), value)])
                crit_attrs.append(conds)

            criteria = [and_(*crit_attr) for crit_attr in crit_attrs]
            criteria_list.append(criteria)

        criteria_list = [and_(*cr) for cr in criteria_list]
        query = query.filter(or_(*criteria_list))

    if limit is not None:
        query = query.limit(limit)

    return query


def _do_artifacts_query(context, session, latest=False):
    """Build the query to get all artifacts based on the context"""

    query = session.query(models.Artifact)

    query = (query.options(joinedload(models.Artifact.properties)).
             options(joinedload(models.Artifact.tags)).
             options(joinedload(models.Artifact.blobs)))

    return _apply_query_base_filters(query, context)


def _apply_query_base_filters(query, context):
    # Don't show deleted artifacts
    query = query.filter(models.Artifact.status != 'deleted')

    # If admin, return everything.
    if context.is_admin:
        return query

    # If anonymous user, return only public artifacts.
    # However, if context.tenant has a value, return both
    # public and private artifacts of the owner.
    if context.tenant is not None:
        query = query.filter(
            or_(models.Artifact.owner == context.tenant,
                models.Artifact.visibility == 'public'))
    else:
        query = query.filter(
            models.Artifact.visibility == 'public')

    return query

op_mappings = {
    'eq': operator.eq,
    'gt': operator.gt,
    'gte': operator.ge,
    'lt': operator.lt,
    'lte': operator.le,
    'neq': operator.ne,
}


def _do_query_filters(filters):
    basic_conds = []
    tag_conds = []
    prop_conds = []
    for field_name, key_name, op, field_type, value in filters:
        if field_name == 'tags':
            tags = utils.split_filter_value_for_quotes(value)
            for tag in tags:
                tag_conds.append([models.ArtifactTag.value == tag])
        elif field_name == 'tags-any':
            tags = utils.split_filter_value_for_quotes(value)
            tag_conds.append([models.ArtifactTag.value.in_(tags)])
        elif field_name in BASE_ARTIFACT_PROPERTIES:
            if op != 'in':
                fn = op_mappings[op]
                if field_name == 'version':
                    value = semver_db.parse(value)
                basic_conds.append([fn(getattr(models.Artifact, field_name),
                                       value)])
            else:
                if field_name == 'version':
                    value = [semver_db.parse(val) for val in value]
                basic_conds.append(
                    [getattr(models.Artifact, field_name).in_(value)])
        else:
            conds = [models.ArtifactProperty.name == field_name]
            if key_name is not None:
                conds.extend([models.ArtifactProperty.key_name == key_name])
            if value is not None:
                if op != 'in':
                    fn = op_mappings[op]
                    conds.extend([fn(getattr(models.ArtifactProperty,
                                             field_type + '_value'), value)])
                else:
                    conds.extend([getattr(models.ArtifactProperty,
                                          field_type + '_value').in_(value)])

            prop_conds.append(conds)

    return basic_conds, tag_conds, prop_conds


def _do_tags(artifact, new_tags):
    tags_to_update = []
    # don't touch existing tags
    for tag in artifact.tags:
        if tag.value in new_tags:
            tags_to_update.append(tag)
            new_tags.remove(tag.value)
    # add new tags
    for tag in new_tags:
        db_tag = models.ArtifactTag()
        db_tag.value = tag
        tags_to_update.append(db_tag)
    return tags_to_update


def _get_prop_type(value):
    if isinstance(value, bool):
        return 'bool_value'
    if isinstance(value, int):
        return 'int_value'
    if isinstance(value, six.string_types):
        return 'string_value'
    if isinstance(value, float):
        return 'numeric_value'


def _create_property(prop_name, prop_value, position=None, key_name=None):
    db_prop = models.ArtifactProperty()
    db_prop.name = prop_name
    setattr(db_prop, _get_prop_type(prop_value), prop_value)
    db_prop.position = position
    db_prop.key_name = key_name
    return db_prop


def _do_properties(artifact, new_properties):
    props_to_update = []
    # don't touch the existing properties
    for prop in artifact.properties:
        if prop.name not in new_properties:
            props_to_update.append(prop)

    for prop_name, prop_value in six.iteritems(new_properties):
        if prop_value is None:
            continue
        if isinstance(prop_value, list):
            for pos, list_prop in enumerate(prop_value):
                for prop in artifact.properties:
                    if prop.name == prop_name and pos == prop.position:
                        if getattr(prop, _get_prop_type(
                                list_prop)) != list_prop:
                            setattr(prop, _get_prop_type(list_prop),
                                    list_prop)
                        props_to_update.append(prop)
                        break
                else:
                    props_to_update.append(
                        _create_property(prop_name, list_prop, position=pos)
                    )
        elif isinstance(prop_value, dict):
            for dict_key, dict_val in six.iteritems(prop_value):
                for prop in artifact.properties:
                    if prop.name == prop_name and prop.key_name == dict_key:
                        if getattr(prop, _get_prop_type(dict_val)) != dict_val:
                            setattr(prop, _get_prop_type(dict_val), dict_val)
                        props_to_update.append(prop)
                        break
                else:
                    props_to_update.append(
                        _create_property(prop_name, dict_val,
                                         key_name=dict_key)
                    )
        elif prop_value is not None:
            for prop in artifact.properties:
                if prop.name == prop_name:
                    setattr(prop, _get_prop_type(prop_value), prop_value)
                    props_to_update.append(prop)
                    break
            else:
                props_to_update.append(_create_property(
                    prop_name, prop_value))

    return props_to_update


def _update_blob_values(blob, values):
    for elem in ('size', 'md5', 'sha1', 'sha256', 'url', 'external', 'status',
                 'content_type'):
        setattr(blob, elem, values[elem])
    return blob


def _do_blobs(artifact, new_blobs):
    blobs_to_update = []
    # don't touch the existing blobs
    for blob in artifact.blobs:
        if blob.name not in new_blobs:
            blobs_to_update.append(blob)

    for blob_name, blob_value in six.iteritems(new_blobs):
        if blob_value is None:
            continue
        if isinstance(blob_value.get('status'), str):
            for blob in artifact.blobs:
                if blob.name == blob_name:
                    _update_blob_values(blob, blob_value)
                    blobs_to_update.append(blob)
                    break
            else:
                blob = models.ArtifactBlob()
                blob.name = blob_name
                _update_blob_values(blob, blob_value)
                blobs_to_update.append(blob)
        else:
            for dict_key, dict_val in six.iteritems(blob_value):
                for blob in artifact.blobs:
                    if blob.name == blob_name and blob.key_name == dict_key:
                        _update_blob_values(blob, dict_val)
                        blobs_to_update.append(blob)
                        break
                else:
                    blob = models.ArtifactBlob()
                    blob.name = blob_name
                    blob.key_name = dict_key
                    _update_blob_values(blob, dict_val)
                    blobs_to_update.append(blob)

    return blobs_to_update


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def create_lock(context, lock_key, session):
    """Try to create lock record."""
    try:
        lock = models.ArtifactLock()
        lock.id = lock_key
        lock.save(session=session)
        return lock.id
    except (sqlalchemy.exc.IntegrityError, db_exception.DBDuplicateEntry):
        msg = _("Cannot lock an item with key %s. "
                "Lock already acquired by other request") % lock_key
        raise exception.Conflict(msg)


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def delete_lock(context, lock_id, session):
    try:
        session.query(models.ArtifactLock).filter_by(id=lock_id).delete()
    except orm.exc.NoResultFound:
        msg = _("Cannot delete a lock with id %s.") % lock_id
        raise exception.NotFound(msg)
