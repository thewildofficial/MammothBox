"""Initial schema with pgvector support

Revision ID: 001_initial
Revises: 
Create Date: 2025-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables for the file allocator system."""

    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create custom ENUM types
    op.execute("CREATE TYPE asset_kind AS ENUM ('media', 'json')")
    op.execute(
        "CREATE TYPE asset_status AS ENUM ('queued', 'processing', 'done', 'failed')")
    op.execute("CREATE TYPE storage_choice AS ENUM ('sql', 'jsonb')")
    op.execute(
        "CREATE TYPE schema_status AS ENUM ('provisional', 'active', 'rejected')")

    # Define ENUM types for reuse (create_type=False since we created them above)
    asset_kind_enum = postgresql.ENUM(
        'media', 'json', name='asset_kind', create_type=False)
    asset_status_enum = postgresql.ENUM(
        'queued', 'processing', 'done', 'failed', name='asset_status', create_type=False)
    storage_choice_enum = postgresql.ENUM(
        'sql', 'jsonb', name='storage_choice', create_type=False)
    schema_status_enum = postgresql.ENUM(
        'provisional', 'active', 'rejected', name='schema_status', create_type=False)

    # Create asset_raw table
    op.create_table(
        'asset_raw',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', sa.String(255), nullable=False, index=True),
        sa.Column('part_id', sa.String(255), nullable=False),
        sa.Column('uri', sa.Text(), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('content_type', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_asset_raw_request_id', 'asset_raw', ['request_id'])

    # Create cluster table
    op.create_table(
        'cluster',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('centroid', postgresql.ARRAY(sa.Float()),
                  nullable=True),  # Will be vector type
        sa.Column('threshold', sa.Float(),
                  nullable=False, server_default='0.8'),
        sa.Column('provisional', sa.Boolean(),
                  nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_cluster_name', 'cluster', ['name'])
    op.create_index('idx_cluster_provisional', 'cluster', ['provisional'])

    # Create schema_def table
    op.create_table(
        'schema_def',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('structure_hash', sa.String(64),
                  nullable=False, unique=True, index=True),
        sa.Column('storage_choice', storage_choice_enum, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('ddl', sa.Text(), nullable=True),
        sa.Column('status', schema_status_enum,
                  nullable=False, server_default='provisional', index=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('field_stability', sa.Float(), nullable=True),
        sa.Column('max_depth', sa.Integer(), nullable=True),
        sa.Column('top_level_keys', sa.Integer(), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('reviewed_by', sa.String(255), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_schema_status', 'schema_def', ['status'])
    op.create_index('idx_schema_structure_hash',
                    'schema_def', ['structure_hash'])

    # Create asset table
    op.create_table(
        'asset',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('kind', asset_kind_enum, nullable=False, index=True),
        sa.Column('uri', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=True, index=True),
        sa.Column('content_type', sa.String(255), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('owner', sa.String(255), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('status', asset_status_enum,
                  nullable=False, server_default='queued', index=True),
        sa.Column('cluster_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('cluster.id'), nullable=True, index=True),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()),
                  nullable=True),  # Will be vector type
        sa.Column('schema_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('schema_def.id'), nullable=True, index=True),
        sa.Column('raw_asset_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_raw.id'), nullable=True),
    )
    op.create_index('idx_asset_kind', 'asset', ['kind'])
    op.create_index('idx_asset_status', 'asset', ['status'])
    op.create_index('idx_asset_owner', 'asset', ['owner'])
    op.create_index('idx_asset_sha256', 'asset', ['sha256'])
    op.create_index('idx_asset_tags', 'asset', [
                    'tags'], postgresql_using='gin')

    # Create lineage table
    op.create_table(
        'lineage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', sa.String(255), nullable=False, index=True),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset.id'), nullable=True, index=True),
        sa.Column('schema_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('schema_def.id'), nullable=True, index=True),
        sa.Column('stage', sa.String(100), nullable=False, index=True),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
        sa.Column('success', sa.Boolean(),
                  nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_lineage_request_id', 'lineage', ['request_id'])
    op.create_index('idx_lineage_asset_id', 'lineage', ['asset_id'])
    op.create_index('idx_lineage_stage', 'lineage', ['stage'])
    op.create_index('idx_lineage_created_at', 'lineage', ['created_at'])

    # Create video_frame table
    op.create_table(
        'video_frame',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset.id'), nullable=False, index=True),
        sa.Column('frame_idx', sa.Integer(), nullable=False),
        sa.Column('timestamp_ms', sa.Integer(), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()),
                  nullable=False),  # Will be vector type
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_video_frame_asset_id', 'video_frame', ['asset_id'])
    op.create_index('idx_video_frame_timestamp',
                    'video_frame', ['timestamp_ms'])

    # Convert array columns to vector type (requires pgvector)
    # This is done after table creation to ensure compatibility
    op.execute(
        "ALTER TABLE cluster ALTER COLUMN centroid TYPE vector(512) USING centroid::vector")
    op.execute(
        "ALTER TABLE asset ALTER COLUMN embedding TYPE vector(512) USING embedding::vector")
    op.execute(
        "ALTER TABLE video_frame ALTER COLUMN embedding TYPE vector(512) USING embedding::vector")


def downgrade() -> None:
    """Drop all tables and extensions."""

    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('video_frame')
    op.drop_table('lineage')
    op.drop_table('asset')
    op.drop_table('schema_def')
    op.drop_table('cluster')
    op.drop_table('asset_raw')

    # Drop custom ENUM types
    op.execute('DROP TYPE IF EXISTS schema_status')
    op.execute('DROP TYPE IF EXISTS storage_choice')
    op.execute('DROP TYPE IF EXISTS asset_status')
    op.execute('DROP TYPE IF EXISTS asset_kind')

    # Drop pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector')
