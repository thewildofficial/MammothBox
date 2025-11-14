"""
Catalog module for database models and operations.

Provides ORM models, database connections, and query utilities.
"""

from src.catalog.models import (
    Base,
    Asset,
    AssetRaw,
    Cluster,
    SchemaDef,
    Lineage,
    VideoFrame,
)
from src.catalog.database import (
    engine,
    SessionLocal,
    init_db,
    get_db,
    get_db_session,
    check_database_connection,
)

__all__ = [
    # Models
    "Base",
    "Asset",
    "AssetRaw",
    "Cluster",
    "SchemaDef",
    "Lineage",
    "VideoFrame",
    # Database
    "engine",
    "SessionLocal",
    "init_db",
    "get_db",
    "get_db_session",
    "check_database_connection",
]
