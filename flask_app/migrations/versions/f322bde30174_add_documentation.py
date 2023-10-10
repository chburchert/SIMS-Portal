"""add documentation

Revision ID: f322bde30174
Revises: 4c3c0ed64178
Create Date: 2023-10-09 16:37:57.705357

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f322bde30174'
down_revision = '4c3c0ed64178'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('documentation', sa.Column('wp_id', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('documentation', 'wp_id')
    # ### end Alembic commands ###
