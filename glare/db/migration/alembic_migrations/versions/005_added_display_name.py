# Copyright 2018 OpenStack Foundation.
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

"""added display name

Revision ID: 005
Revises: 004
Create Date: 2018-03-13 14:32:33.765690

"""

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('glare_artifacts', sa.Column('display_type_name',
                                               sa.String(255),
                                               nullable=True))
    op.create_index('ix_glare_artifact_display_name',
                    'glare_artifacts',
                    ['display_type_name']
                    )


def downgrade():
    with op.batch_alter_table('glare_artifacts') as batch_op:
        batch_op.drop_index('ix_glare_artifact_display_name')
        batch_op.drop_column('display_type_name')
