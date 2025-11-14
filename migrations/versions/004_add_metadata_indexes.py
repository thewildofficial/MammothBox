"""Add metadata and performance indexes

Revision ID: 004_add_metadata_indexes
Revises: 003_add_unique_constraint_job_request_id
Create Date: 2025-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_add_metadata_indexes'
down_revision: Union[str, None] = '003_add_unique_constraint_job_request_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GIN indexes for JSONB metadata queries and composite indexes for common query patterns."""
    
    # GIN index for JSONB metadata (perceptual hash lookups, OCR text searches)
    # Using jsonb_path_ops for better performance with containment queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_metadata_gin 
        ON asset USING GIN (metadata jsonb_path_ops);
    """)
    
    # Composite index for common query patterns (status, media_type, created_at)
    # This optimizes filtering by status and type with time-based sorting
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_status_kind_created 
        ON asset (status, kind, created_at DESC);
    """)
    
    # Note: tags GIN index already exists in initial migration (idx_asset_tags)
    # Verify it exists, create if missing
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_tags_gin 
        ON asset USING GIN (tags);
    """)


def downgrade() -> None:
    """Remove metadata and performance indexes."""
    
    # Drop indexes in reverse order
    op.execute('DROP INDEX IF EXISTS idx_asset_tags_gin')
    op.execute('DROP INDEX IF EXISTS idx_asset_status_kind_created')
    op.execute('DROP INDEX IF EXISTS idx_asset_metadata_gin')

