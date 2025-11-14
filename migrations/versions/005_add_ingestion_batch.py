"""Add ingestion_batch table for folder ingestion tracking

Revision ID: 005_add_ingestion_batch
Revises: 004_add_metadata_indexes
Create Date: 2025-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005_add_ingestion_batch'
down_revision: Union[str, None] = '004_add_metadata_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ingestion_batch table for tracking folder ingestion progress."""
    
    # Create batch_status ENUM type
    op.execute("CREATE TYPE batch_status AS ENUM ('pending', 'processing', 'completed', 'failed')")
    
    # Define ENUM type for reuse
    batch_status_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed',
        name='batch_status',
        create_type=False
    )
    
    # Create ingestion_batch table
    op.create_table(
        'ingestion_batch',
        sa.Column('batch_id', sa.String(255), primary_key=True),
        sa.Column('folder_path', sa.String(500), nullable=False),
        sa.Column('status', batch_status_enum, nullable=False, server_default='pending'),
        sa.Column('total_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_files', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('failed_files', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('user_comment', sa.Text(), nullable=True),
        sa.Column('owner', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    
    # Create indexes
    op.create_index('idx_ingestion_batch_status', 'ingestion_batch', ['status'])
    op.create_index('idx_ingestion_batch_owner', 'ingestion_batch', ['owner'])
    op.create_index('idx_ingestion_batch_created_at', 'ingestion_batch', ['created_at'])


def downgrade() -> None:
    """Remove ingestion_batch table."""
    
    # Drop indexes
    op.drop_index('idx_ingestion_batch_created_at', table_name='ingestion_batch')
    op.drop_index('idx_ingestion_batch_owner', table_name='ingestion_batch')
    op.drop_index('idx_ingestion_batch_status', table_name='ingestion_batch')
    
    # Drop table
    op.drop_table('ingestion_batch')
    
    # Drop ENUM type
    op.execute('DROP TYPE IF EXISTS batch_status')

