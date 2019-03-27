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

import hashlib
import operator
import threading

from oslo_config import cfg
from oslo_db import exception as db_exception
from oslo_db import options
from oslo_db.sqlalchemy import session
from oslo_log import log as os_logging
from oslo_utils import timeutils
import osprofiler.sqlalchemy
from retrying import retry
import six
import sqlalchemy
from sqlalchemy import and_, distinct
import sqlalchemy.exc
from sqlalchemy import exists
from sqlalchemy import func
from sqlalchemy import or_
import sqlalchemy.orm as orm
from sqlalchemy.orm import aliased
from sqlalchemy.orm import joinedload

from glare.common import exception
from glare.common import semver_db
from glare.common import utils
from glare.db.sqlalchemy import models
from glare.i18n import _

LOG = os_logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group("profiler", "glare.common.wsgi")
options.set_defaults(CONF)


BASE_ARTIFACT_PROPERTIES = ('id', 'visibility', 'created_at', 'updated_at',
                            'activated_at', 'owner', 'status', 'description',
                            'name', 'type_name', 'version',
                            'display_type_name')

_FACADE = None
_LOCK = threading.Lock()


def _retry_on_deadlock(exc):
    """Decorator to retry a DB API call if Deadlock was received."""

    if isinstance(exc, db_exception.DBDeadlock):
        LOG.warning("Deadlock detected. Retrying...")
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


def setup_db():
    engine = get_engine()
    models.register_models(engine)


def drop_db():
    engine = get_engine()
    models.unregister_models(engine)


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def delete(context, artifact_id, session):
    with session.begin():
        session.query(models.Artifact).filter_by(id=artifact_id).delete()


def _drop_protected_attrs(model_class, values):
    """Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
@utils.no_4byte_params
def create_or_update(context, artifact_id, values, session):
    with session.begin():
        _drop_protected_attrs(models.Artifact, values)
        if artifact_id is None:
            # create new artifact
            artifact = models.Artifact()
            artifact.id = values.pop('id')
        else:
            # update the existing artifact
            artifact = _get(context, None, artifact_id, session)

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
        if 'status' in values:
            if session.query(exists().where(and_(
                models.ArtifactBlob.status == 'saving',
                models.ArtifactBlob.artifact_id == artifact_id))
            ).one()[0]:
                raise exception.Conflict(
                    "You cannot change artifact status if it has "
                    "uploading blobs.")
            if values['status'] == 'active':
                artifact.activated_at = timeutils.utcnow()
        artifact.update(values)

        artifact.save(session=session)
        LOG.debug("Response from the database was received.")

        return artifact.to_dict()


def _get(context, type_name, artifact_id, session, get_any_artifact=False):
    try:
        query = _do_artifacts_query(
            context, session, list_all_artifacts=get_any_artifact).\
            filter_by(id=artifact_id)
        if type_name is not None:
            query = query.filter_by(type_name=type_name)
        artifact = query.one()
    except orm.exc.NoResultFound:
        msg = _("Artifact with id=%s not found.") % artifact_id
        LOG.warning(msg)
        raise exception.ArtifactNotFound(msg)
    return artifact


def get(context, type_name, artifact_id, session, get_any_artifact=False):
    return _get(context, type_name, artifact_id,
                session, get_any_artifact).to_dict()


def get_all(context, session, filters=None, marker=None, limit=None,
            sort=None, latest=False, list_all_artifacts=False):
    """List all visible artifacts

    :param filters: dict of filter keys and values.
    :param marker: artifact id after which to start page
    :param limit: maximum number of artifacts to return
    :param sort: a tuple (key, dir, type) where key is an attribute by
     which results should be sorted, dir is a direction: 'asc' or 'desc',
     and type is type of the attribute: 'bool', 'string', 'numeric' or 'int' or
     None if attribute is base.
     :param list_all_artifacts: flag that indicate, if the list should
     return artifact from all realms (True),
     or from the specific realm (False)
    :param latest: flag that indicates, that only artifacts with highest
     versions should be returned in output
    """
    artifacts = _get_all(
        context, session, filters, marker,
        limit, sort, latest, list_all_artifacts)
    total_artifacts_count = get_artifact_count(context, session, filters,
                                               latest)
    return {
        "artifacts": [af.to_dict() for af in artifacts],
        "total_count": total_artifacts_count
    }


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

    or_queries = []
    if basic_conds:
        for basic_condition in basic_conds['and']:
            query = query.filter(and_(*basic_condition))
        for basic_condition in basic_conds['or']:
            or_queries.append(*basic_condition)

    if tag_conds:
        for tag_condition in tag_conds['and']:
            query = query.join(models.ArtifactTag, aliased=True).filter(
                and_(*tag_condition))
        tag_or_queries = []
        for tag_condition in tag_conds['or']:
            artifact_tag_alias = aliased(models.ArtifactTag)
            query = query.outerjoin(artifact_tag_alias)
            for tag_cond in tag_condition:
                tag_cond.left = artifact_tag_alias.value
            tag_or_queries.append(and_(*tag_condition))
        # If tag_or_queries is blank, there will not be any effect on query
        or_queries.append(and_(*tag_or_queries))

    if prop_conds:
        for prop_condition in prop_conds['and']:
            query = query.join(models.ArtifactProperty, aliased=True).filter(
                and_(*prop_condition))
        for prop_condition in prop_conds['or']:
            or_queries.append(and_(*prop_condition))

    if len(or_queries) != 0:
        if len(prop_conds['or']) > 0:
            query = query.join(models.ArtifactProperty, aliased=True)

        query = query.filter(or_(*or_queries))

    return query


def _get_all(context, session, filters=None, marker=None, limit=None,
             sort=None, latest=False, list_all_artifacts=False):

    filters = filters or {}

    query = _do_artifacts_query(context, session, list_all_artifacts)

    basic_conds, tag_conds, prop_conds = _do_query_filters(filters)

    query = _apply_user_filters(query, basic_conds, tag_conds, prop_conds)

    if latest:
        query = _apply_latest_filter(context, session, query,
                                     basic_conds, tag_conds, prop_conds)

    marker_artifact = None
    if marker is not None:
        marker_artifact = get(context, None, marker, session)

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
        query = query.group_by(models.Artifact.id)
        query = query.limit(limit)

    return query


def _do_artifacts_query(context, session, list_all_artifacts=False):
    """Build the query to get all artifacts based on the context"""

    query = session.query(models.Artifact)

    query = (query.options(joinedload(models.Artifact.properties)).
             options(joinedload(models.Artifact.tags)).
             options(joinedload(models.Artifact.blobs)))

    return _apply_query_base_filters(query, context, list_all_artifacts)


def _apply_query_base_filters(query, context, list_all_artifacts=False):
    # If admin, return everything.
    if context.is_admin or list_all_artifacts:
        return query

    # If anonymous user, return only public artifacts.
    # However, if context.project_id has a value, return both
    # public and private artifacts of the owner.
    if context.project_id is not None:
        query = query.filter(
            or_(models.Artifact.owner == context.project_id,
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
    basic_conds = {
        "and": [],
        "or": []
    }
    tag_conds = {
        "and": [],
        "or": []
    }
    prop_conds = {
        "and": [],
        "or": []
    }
    for field_name, key_name, op, field_type, value, query_combiner in filters:
        if field_name == 'tags':
            tags = utils.split_filter_value_for_quotes(value)
            for tag in tags:
                tag_conds[query_combiner].append(
                    [models.ArtifactTag.value == tag])
        elif field_name == 'tags-any':
            tags = utils.split_filter_value_for_quotes(value)
            tag_conds[query_combiner].append(
                [models.ArtifactTag.value.in_(tags)])
        elif field_name in BASE_ARTIFACT_PROPERTIES:
            if op == 'in':
                if field_name == 'version':
                    value = [semver_db.parse(val) for val in value]
                    basic_conds[query_combiner].append(
                        [or_(*[
                            models.Artifact.version == ver for ver in value])])
                else:
                    basic_conds[query_combiner].append(
                        [getattr(models.Artifact, field_name).in_(value)])
            elif op == 'like':
                basic_conds[query_combiner].append(
                    [getattr(models.Artifact, field_name).like(value)])
            else:
                fn = op_mappings[op]
                if field_name == 'version':
                    value = semver_db.parse(value)
                basic_conds[query_combiner].append(
                    [fn(getattr(models.Artifact, field_name), value)])
        else:
            conds = [models.ArtifactProperty.name == field_name]
            if key_name is not None:
                if op == 'eq' or value is not None:
                    conds.extend(
                        [models.ArtifactProperty.key_name == key_name])
                elif op == 'in':
                    conds.extend(
                        [models.ArtifactProperty.key_name.in_(key_name)])
            if value is not None:
                if op == 'in':
                    conds.extend([getattr(models.ArtifactProperty,
                                          field_type + '_value').in_(value)])
                elif op == 'like':
                    conds.extend(
                        [models.ArtifactProperty.string_value.like(value)])
                else:
                    fn = op_mappings[op]
                    conds.extend([fn(getattr(models.ArtifactProperty,
                                             field_type + '_value'), value)])

            prop_conds[query_combiner].append(conds)

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

    for prop_name, prop_value in new_properties.items():
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
            for dict_key, dict_val in prop_value.items():
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

    for blob_name, blob_value in new_blobs.items():
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
            for dict_key, dict_val in blob_value.items():
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


def count_artifact_number(context, session, type_name=None):
    """Return a number of artifacts for tenant."""
    query = session.query(func.count(models.Artifact.id)).filter(
        models.Artifact.owner == context.project_id)
    if type_name is not None:
        query = query.filter(models.Artifact.type_name == type_name)
    return query.order_by(None).scalar() or 0


def calculate_uploaded_data(context, session, type_name=None):
    """Return the amount of uploaded data for tenant."""
    query = session.query(
        func.sum(models.ArtifactBlob.size)).join(
        models.Artifact, aliased=True).filter(
        models.Artifact.owner == context.project_id)
    if type_name is not None:
        query = query.filter(models.Artifact.type_name == type_name)
    return query.order_by(None).scalar() or 0


def _generate_quota_id(project_id, quota_name, type_name=None):
    quota_id = b"%s:%s" % (project_id.encode(), quota_name.encode())
    if type_name is not None:
        quota_id += b":%s" % type_name.encode()
    return hashlib.md5(quota_id).hexdigest()


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
@utils.no_4byte_params
def set_quotas(values, session):
    """Create new quota instances in database"""
    with session.begin():
        for project_id, project_quotas in values.items():

            # reset all project quotas
            session.query(models.ArtifactQuota).filter(
                models.ArtifactQuota.project_id == project_id).delete()

            # generate new quotas
            for quota_name, quota_value in project_quotas.items():
                q = models.ArtifactQuota()
                q.project_id = project_id
                q.quota_name = quota_name
                q.quota_value = quota_value
                session.add(q)

        # save all quotas
        session.flush()


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def get_all_quotas(session, project_id=None):
    """List all available quotas."""
    query = session.query(models.ArtifactQuota)
    if project_id is not None:
        query = query.filter(
            models.ArtifactQuota.project_id == project_id)
    quotas = query.order_by(models.ArtifactQuota.project_id).all()

    res = {}
    for quota in quotas:
        res.setdefault(
            quota.project_id, {})[quota.quota_name] = quota.quota_value

    return res


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
@utils.no_4byte_params
def create_lock(context, lock_key, session):
    """Try to create lock record."""
    with session.begin():
        existing = session.query(models.ArtifactLock).get(lock_key)
        if existing is None:
            try:
                lock = models.ArtifactLock()
                lock.id = lock_key
                lock.save(session=session)
                return lock.id
            except (sqlalchemy.exc.IntegrityError,
                    db_exception.DBDuplicateEntry):
                msg = _("Cannot lock an item with key %s. "
                        "Lock already acquired by other request") % lock_key
                raise exception.Conflict(msg)
        else:
            if timeutils.is_older_than(existing.acquired_at, 5):
                existing.acquired_at = timeutils.utcnow()
                existing.save(session)
                return existing.id
            else:
                msg = _("Cannot lock an item with key %s. "
                        "Lock already acquired by other request") % lock_key
                raise exception.Conflict(msg)


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def delete_lock(context, lock_id, session):
    with session.begin():
        session.query(models.ArtifactLock).filter_by(id=lock_id).delete()


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def save_blob_data(context, blob_data_id, data, session):
    """Save blob data to database."""
    LOG.debug("Starting Blob data upload in database for %s", blob_data_id)
    try:
        with session.begin():
            blob_data = models.ArtifactBlobData()
            blob_data.id = blob_data_id
            blob_data.data = data.read()
            blob_data.save(session=session)
            return "sql://" + blob_data.id
    except Exception as e:
        LOG.error("Exception received during blob upload %s", e)
        raise


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def save_blob_data_batch(context, blobs, session):
    """Perform batch uploading to database."""
    with session.begin():

        locations = []

        # blobs is a list of tuples (blob_data_id, data)
        for blob_data_id, data in blobs:
            blob_data = models.ArtifactBlobData()
            blob_data.id = blob_data_id
            blob_data.data = b''
            while True:
                chunk = data.read()
                if chunk:
                    blob_data.data += chunk
                else:
                    break
            session.add(blob_data)
            locations.append("sql://" + blob_data.id)

        session.flush()

    return locations


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def get_blob_data(context, uri, session):
    """Download blob data from database."""

    blob_data_id = uri[6:]
    try:
        blob_data = session.query(
            models.ArtifactBlobData).filter_by(id=blob_data_id).one()
    except orm.exc.NoResultFound:
        msg = _("Cannot find a blob data with id %s.") % blob_data_id
        raise exception.NotFound(msg)
    return blob_data.data


@retry(retry_on_exception=_retry_on_deadlock, wait_fixed=500,
       stop_max_attempt_number=50)
def delete_blob_data(context, uri, session):
    """Delete blob data from database."""
    with session.begin():
        blob_data_id = uri[6:]
        session.query(
            models.ArtifactBlobData).filter_by(id=blob_data_id).delete()


def get_artifact_count(context, session, filters=None, latest=False,
                       list_all_artifacts=False):

    filters = filters or {}

    query = _create_artifact_count_query(context, session, list_all_artifacts)

    basic_conds, tag_conds, prop_conds = _do_query_filters(filters)

    query = _apply_user_filters(query, basic_conds, tag_conds, prop_conds)

    if latest:
        query = _apply_latest_filter(context, session, query,
                                     basic_conds, tag_conds, prop_conds)

    return query.all()[0].total_count


def _create_artifact_count_query(context, session, list_all_artifacts):

    query = session.query(func.count(distinct(models.Artifact.id))
                          .label("total_count"))

    return _apply_query_base_filters(query, context, list_all_artifacts)
