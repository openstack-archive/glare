# Copyright 2017 OpenStack Foundation.
#
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

"""Add acquired_at column

Revision ID: 003
Revises: 002
Create Date: 2017-01-10 12:53:25.108149

"""

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

MYSQL_ENGINE = 'InnoDB'
MYSQL_CHARSET = 'utf8'


def upgrade():
    op.create_table(
        'glare_blob_data',
        sa.Column('id', sa.String(255), primary_key=True, nullable=False),
        # Because of strange behavior of mysql LargeBinary is converted to
        # BLOB instead of LONGBLOB. So we have to fix it explicitly with
        # 'with_variant' call.
        sa.Column(
            'data',
            sa.LargeBinary().with_variant(mysql.LONGBLOB(), 'mysql'),
            nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine=MYSQL_ENGINE,
        mysql_charset=MYSQL_CHARSET
    )


def downgrade():
    op.drop_table('glare_blob_data')
