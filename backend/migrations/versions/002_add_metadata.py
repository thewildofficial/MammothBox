"""
Add metadata JSONB fields to Cluster and Asset models.

Revision ID: 002_add_metadata
Revises: 001_initial
Create Date: 2025-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '002_add_metadata'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    """Add metadata JSONB columns to clusters and assets tables."""
    # Add metadata to clusters table
    op.add_column('clusters', sa.Column('metadata', JSONB, nullable=True))

    # Add metadata to assets table
    op.add_column('assets', sa.Column('metadata', JSONB, nullable=True))


def downgrade():
    """Remove metadata columns."""
    op.drop_column('clusters', 'metadata')
    op.drop_column('assets', 'metadata')
