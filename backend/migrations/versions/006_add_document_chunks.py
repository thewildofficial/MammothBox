"""Add document chunk storage and extend asset kind for documents.

Revision ID: 006_add_document_chunks
Revises: 005_add_ingestion_batch
Create Date: 2025-11-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "006_add_document_chunks"
down_revision: Union[str, None] = "005_add_ingestion_batch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add document_chunk table and extend asset kind enum."""

    # Extend asset kind enum to support documents
    op.execute("ALTER TYPE asset_kind ADD VALUE IF NOT EXISTS 'document'")

    # Parent-child lineage for embedded media
    op.add_column(
        "asset",
        sa.Column(
            "parent_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_asset_parent_asset_id", "asset", ["parent_asset_id"], unique=False
    )

    op.create_table(
        "document_chunk",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parent_heading", sa.String(length=500), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("element_type", sa.String(length=100), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_document_chunk_asset_id", "document_chunk", ["asset_id"], unique=False
    )
    op.create_index(
        "idx_document_chunk_chunk_index",
        "document_chunk",
        ["chunk_index"],
        unique=False,
    )

    # HNSW index for 768-d vectors
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunk_embedding_hnsw
        ON document_chunk
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )


def downgrade() -> None:
    """Drop document chunk storage (enum value remains for forward compatibility)."""

    op.execute(
        "DROP INDEX IF EXISTS idx_document_chunk_embedding_hnsw"
    )
    op.drop_index("idx_document_chunk_chunk_index", table_name="document_chunk")
    op.drop_index("idx_document_chunk_asset_id", table_name="document_chunk")
    op.drop_table("document_chunk")
    op.drop_index("idx_asset_parent_asset_id", table_name="asset")
    op.drop_column("asset", "parent_asset_id")

