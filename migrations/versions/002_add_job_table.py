"""Add job queue table

Revision ID: 002_add_job_table
Revises: 001_initial
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_job_table'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add job table for async processing queue."""
    
    # Create job_type and job_status ENUM types
    op.execute("CREATE TYPE job_type AS ENUM ('media', 'json')")
    op.execute(
        "CREATE TYPE job_status AS ENUM ('queued', 'processing', 'done', 'failed')")
    
    # Define ENUM types for reuse
    job_type_enum = postgresql.ENUM(
        'media', 'json', name='job_type', create_type=False)
    job_status_enum = postgresql.ENUM(
        'queued', 'processing', 'done', 'failed', name='job_status', create_type=False)
    
    # Create job table
    op.create_table(
        'job',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', sa.String(255), nullable=False, index=True),
        sa.Column('job_type', job_type_enum, nullable=False, index=True),
        sa.Column('status', job_status_enum, nullable=False, 
                  server_default='queued', index=True),
        sa.Column('job_data', postgresql.JSONB(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True, index=True),
        sa.Column('dead_letter', sa.Boolean(), nullable=False, 
                  server_default='false', index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('asset_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()'), index=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    
    # Create additional indexes
    op.create_index('idx_job_request_id', 'job', ['request_id'])
    op.create_index('idx_job_status', 'job', ['status'])
    op.create_index('idx_job_type', 'job', ['job_type'])
    op.create_index('idx_job_dead_letter', 'job', ['dead_letter'])
    op.create_index('idx_job_next_retry_at', 'job', ['next_retry_at'])
    op.create_index('idx_job_created_at', 'job', ['created_at'])


def downgrade() -> None:
    """Remove job table."""
    
    # Drop indexes
    op.drop_index('idx_job_created_at', table_name='job')
    op.drop_index('idx_job_next_retry_at', table_name='job')
    op.drop_index('idx_job_dead_letter', table_name='job')
    op.drop_index('idx_job_type', table_name='job')
    op.drop_index('idx_job_status', table_name='job')
    op.drop_index('idx_job_request_id', table_name='job')
    
    # Drop table
    op.drop_table('job')
    
    # Drop ENUM types
    op.execute('DROP TYPE IF EXISTS job_status')
    op.execute('DROP TYPE IF EXISTS job_type')




