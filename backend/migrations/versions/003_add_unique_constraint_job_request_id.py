"""Add unique constraint on job.request_id

Revision ID: 003_add_unique_constraint_job_request_id
Revises: 002_add_job_table
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_add_unique_constraint_job_request_id'
down_revision: Union[str, None] = '002_add_job_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint on job.request_id for idempotency."""
    
    # Drop the existing non-unique index if it exists
    op.drop_index('idx_job_request_id', table_name='job')
    
    # Add unique constraint (this creates a unique index automatically)
    op.create_unique_constraint('uq_job_request_id', 'job', ['request_id'])


def downgrade() -> None:
    """Remove unique constraint on job.request_id."""
    
    # Drop the unique constraint
    op.drop_constraint('uq_job_request_id', 'job', type_='unique')
    
    # Recreate the non-unique index
    op.create_index('idx_job_request_id', 'job', ['request_id'])

