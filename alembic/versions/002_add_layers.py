"""Add layers table

Revision ID: 002_add_layers
Revises: 001
Create Date: 2026-01-06 10:18:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_layers'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create layers table
    op.create_table(
        'layers',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, comment='Layer name (e.g., COUNTY, BUILDINGS)'),
        sa.Column('url', sa.String(length=1000), nullable=False, comment='Full ArcGIS REST service URL'),
        sa.Column('layer_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Field definitions with name and type'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('geometry_type', sa.String(length=50), nullable=True, comment='Point, Polyline, Polygon, etc.'),
        sa.Column('is_active', sa.Integer(), nullable=False, comment='1=active, 0=inactive'),
        sa.Column('last_fetched', sa.DateTime(), nullable=True, comment='Last time layer info was fetched'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_layers_id'), 'layers', ['id'], unique=False)
    op.create_index(op.f('ix_layers_name'), 'layers', ['name'], unique=True)
    
    # Set default value for is_active
    op.execute("ALTER TABLE layers ALTER COLUMN is_active SET DEFAULT 1")


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_layers_name'), table_name='layers')
    op.drop_index(op.f('ix_layers_id'), table_name='layers')
    
    # Drop table
    op.drop_table('layers')
