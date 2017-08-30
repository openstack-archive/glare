# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Initial version

Revision ID: 001
Revises: None
Create Date: 2016-08-18 12:28:37.372366

"""

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None

from alembic import op
import sqlalchemy as sa


MYSQL_ENGINE = 'InnoDB'
MYSQL_CHARSET = 'utf8'


def upgrade():
    op.create_table(
        'glare_artifacts',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type_name', sa.String(255), nullable=False),
        sa.Column('version_prefix', sa.BigInteger(), nullable=False),
        sa.Column('version_suffix', sa.String(255)),
        sa.Column('version_meta', sa.String(255)),
        sa.Column('description', sa.Text()),
        sa.Column('visibility', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('owner', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('activated_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )

    op.create_index('ix_glare_artifact_name_and_version',
                    'glare_artifacts',
                    ['name', 'version_prefix', 'version_suffix']
                    )
    op.create_index('ix_glare_artifact_type',
                    'glare_artifacts',
                    ['type_name']
                    )
    op.create_index('ix_glare_artifact_status',
                    'glare_artifacts',
                    ['status']
                    )
    op.create_index('ix_glare_artifact_owner',
                    'glare_artifacts',
                    ['owner']
                    )
    op.create_index('ix_glare_artifact_visibility',
                    'glare_artifacts',
                    ['visibility']
                    )

    op.create_table(
        'glare_artifact_tags',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('artifact_id', sa.String(36),
                  sa.ForeignKey('glare_artifacts.id'), nullable=False),
        sa.Column('value', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )

    op.create_index('ix_glare_artifact_tags_artifact_id',
                    'glare_artifact_tags',
                    ['artifact_id']
                    )
    op.create_index('ix_glare_artifact_tags_artifact_id_tag_value',
                    'glare_artifact_tags',
                    ['artifact_id', 'value']
                    )

    op.create_table(
        'glare_artifact_blobs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('artifact_id', sa.String(36),
                  sa.ForeignKey('glare_artifacts.id'), nullable=False),
        sa.Column('size', sa.BigInteger()),
        sa.Column('md5', sa.String(32)),
        sa.Column('sha1', sa.String(40)),
        sa.Column('sha256', sa.String(64)),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('external', sa.Boolean()),
        sa.Column('url', sa.Text()),
        sa.Column('key_name', sa.String(2048)),
        sa.Column('content_type', sa.String(255)),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )

    op.create_index('ix_glare_artifact_blobs_artifact_id',
                    'glare_artifact_blobs',
                    ['artifact_id']
                    )
    op.create_index('ix_glare_artifact_blobs_name',
                    'glare_artifact_blobs',
                    ['name']
                    )

    op.create_table(
        'glare_artifact_properties',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('artifact_id', sa.String(36),
                  sa.ForeignKey('glare_artifacts.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('string_value', sa.String(20000)),
        sa.Column('int_value', sa.Integer()),
        sa.Column('numeric_value', sa.Numeric()),
        sa.Column('bool_value', sa.Boolean()),
        sa.Column('position', sa.Integer()),
        sa.Column('key_name', sa.String(255)),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )

    op.create_index('ix_glare_artifact_properties_artifact_id',
                    'glare_artifact_properties',
                    ['artifact_id']
                    )
    op.create_index('ix_glare_artifact_properties_name',
                    'glare_artifact_properties',
                    ['name']
                    )

    op.create_table(
        'glare_artifact_locks',
        sa.Column('id', sa.String(255), primary_key=True, nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )


def downgrade():
    op.drop_table('glare_artifact_locks')
    op.drop_table('glare_artifact_properties')
    op.drop_table('glare_artifact_blobs')
    op.drop_table('glare_artifact_tags')
    op.drop_table('glare_artifacts')

    # end Alembic commands #
