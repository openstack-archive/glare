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


from oslo_db.sqlalchemy import models
from oslo_utils import timeutils
from oslo_utils import uuidutils
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy.ext import declarative
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import LargeBinary
from sqlalchemy import Numeric
from sqlalchemy.orm import backref
from sqlalchemy.orm import composite
from sqlalchemy.orm import relationship
from sqlalchemy import String
from sqlalchemy import Text

from glare.common import semver_db

BASE = declarative.declarative_base()


class ArtifactBase(models.ModelBase):
    """Base class for Artifact Models."""

    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
    __table_initialized__ = False

    def save(self, session=None):
        from glare.db.sqlalchemy import api as db_api

        super(ArtifactBase, self).save(session or db_api.get_session())

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def to_dict(self):
        d = {}
        for c in self.__table__.columns:
            d[c.name] = self[c.name]
        return d


def _parse_property_value(prop):
    columns = [
        'int_value',
        'string_value',
        'bool_value',
        'numeric_value']

    for prop_type in columns:
        if getattr(prop, prop_type) is not None:
            return getattr(prop, prop_type)


def _parse_blob_value(blob):
    return {
        "id": blob.id,
        "url": blob.url,
        "status": blob.status,
        "external": blob.external,
        "md5": blob.md5,
        "sha1": blob.sha1,
        "sha256": blob.sha256,
        "size": blob.size,
        "content_type": blob.content_type
    }


class Artifact(BASE, ArtifactBase):
    __tablename__ = 'glare_artifacts'
    __table_args__ = (
        Index('ix_glare_artifact_name_and_version', 'name', 'version_prefix',
              'version_suffix'),
        Index('ix_glare_artifact_type', 'type_name'),
        Index('ix_glare_artifact_status', 'status'),
        Index('ix_glare_artifact_owner', 'owner'),
        Index('ix_glare_artifact_visibility', 'visibility'),
        Index('ix_glare_artifact_display_name', 'display_type_name'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'})
    __protected_attributes__ = set(["created_at", "updated_at"])

    id = Column(String(36), primary_key=True,
                default=lambda: uuidutils.generate_uuid())
    name = Column(String(255), nullable=False)
    type_name = Column(String(255), nullable=False)
    version_prefix = Column(BigInteger().with_variant(Integer, "sqlite"),
                            nullable=False)
    version_suffix = Column(String(255))
    version_meta = Column(String(255))
    version = composite(semver_db.DBVersion, version_prefix,
                        version_suffix, version_meta,
                        comparator_factory=semver_db.VersionComparator)
    description = Column(Text())
    visibility = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    owner = Column(String(255))
    created_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False)
    updated_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False, onupdate=lambda: timeutils.utcnow())
    activated_at = Column(DateTime)
    display_type_name = Column(String(255), nullable=True)

    def to_dict(self):
        d = super(Artifact, self).to_dict()

        d.pop('version_prefix')
        d.pop('version_suffix')
        d.pop('version_meta')
        d['version'] = str(self.version)

        # parse tags
        tags = []
        for tag in self.tags:
            tags.append(tag.value)
        d['tags'] = tags

        # parse properties
        for prop in self.properties:
            prop_value = _parse_property_value(prop)

            if prop.position is not None:
                if prop.name not in d:
                    # create new list
                    d[prop.name] = []
                # insert value in position
                d[prop.name].insert(prop.position, prop_value)
            elif prop.key_name is not None:
                if prop.name not in d:
                    # create new dict
                    d[prop.name] = {}
                # insert value in the dict
                d[prop.name][prop.key_name] = prop_value
            else:
                # make scalar
                d[prop.name] = prop_value

        # parse blobs
        for blob in self.blobs:
            blob_value = _parse_blob_value(blob)
            if blob.key_name is not None:
                if blob.name not in d:
                    # create new dict
                    d[blob.name] = {}
                # insert value in the dict
                d[blob.name][blob.key_name] = blob_value
            else:
                # make scalar
                d[blob.name] = blob_value

        return d


class ArtifactTag(BASE, ArtifactBase):
    __tablename__ = 'glare_artifact_tags'
    __table_args__ = (Index('ix_glare_artifact_tags_artifact_id_tag_value',
                            'artifact_id', 'value'),
                      Index('ix_glare_artifact_tags_artifact_id',
                            'artifact_id'),
                      {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)

    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: uuidutils.generate_uuid())
    artifact_id = Column(String(36), ForeignKey('glare_artifacts.id'),
                         nullable=False)
    artifact = relationship(Artifact,
                            backref=backref('tags',
                                            cascade="all, delete-orphan"))
    value = Column(String(255), nullable=False)


class ArtifactProperty(BASE, ArtifactBase):
    __tablename__ = 'glare_artifact_properties'
    __table_args__ = (
        Index('ix_glare_artifact_properties_artifact_id', 'artifact_id'),
        Index('ix_glare_artifact_properties_name', 'name'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: uuidutils.generate_uuid())
    artifact_id = Column(String(36), ForeignKey('glare_artifacts.id'),
                         nullable=False)
    artifact = relationship(Artifact,
                            backref=backref('properties',
                                            cascade="all, delete-orphan"))
    name = Column(String(255), nullable=False)
    string_value = Column(String(20000))
    int_value = Column(Integer)
    numeric_value = Column(Numeric)
    bool_value = Column(Boolean)
    position = Column(Integer)
    key_name = Column(String(255))


class ArtifactBlob(BASE, ArtifactBase):
    __tablename__ = 'glare_artifact_blobs'
    __table_args__ = (
        Index('ix_glare_artifact_blobs_artifact_id', 'artifact_id'),
        Index('ix_glare_artifact_blobs_name', 'name'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: uuidutils.generate_uuid())
    artifact_id = Column(String(36), ForeignKey('glare_artifacts.id'),
                         nullable=False)
    name = Column(String(255), nullable=False)
    size = Column(BigInteger().with_variant(Integer, "sqlite"))
    md5 = Column(String(32))
    sha1 = Column(String(40))
    sha256 = Column(String(64))
    external = Column(Boolean)
    url = Column(Text)
    status = Column(String(32), nullable=False)
    key_name = Column(String(2048))
    content_type = Column(String(255))
    artifact = relationship(Artifact,
                            backref=backref('blobs',
                                            cascade="all, delete-orphan"))


class ArtifactLock(BASE, ArtifactBase):
    __tablename__ = 'glare_artifact_locks'
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(255), primary_key=True, nullable=False)
    acquired_at = Column(
        DateTime, nullable=False, default=lambda: timeutils.utcnow())


class ArtifactBlobData(BASE, ArtifactBase):
    __tablename__ = 'glare_blob_data'
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(255), primary_key=True, nullable=False)
    data = Column(LargeBinary(length=(2 ** 32) - 1), nullable=False)


class ArtifactQuota(BASE, ArtifactBase):
    __tablename__ = 'glare_quotas'
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    project_id = Column(String(255), primary_key=True)
    quota_name = Column(String(32), primary_key=True)
    quota_value = Column(BigInteger().with_variant(Integer, "sqlite"),
                         nullable=False)


def register_models(engine):
    """Create database tables for all models with the given engine."""
    models = (Artifact, ArtifactTag, ArtifactProperty, ArtifactBlob,
              ArtifactLock, ArtifactQuota)
    for model in models:
        model.metadata.create_all(engine)


def unregister_models(engine):
    """Drop database tables for all models with the given engine."""
    models = (ArtifactQuota, ArtifactLock, ArtifactBlob, ArtifactProperty,
              ArtifactTag, Artifact)
    for model in models:
        model.metadata.drop_all(engine)
