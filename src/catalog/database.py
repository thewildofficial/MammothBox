"""
Database connection and session management.

Provides database engine, session factory, and helper functions
for database operations.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from src.config.settings import get_settings
from src.catalog.models import Base

settings = get_settings()

# Create database engine with optimized connection pooling
# QueuePool maintains a pool of connections for reuse, reducing connection overhead
# pool_size: Number of connections maintained in the pool
# max_overflow: Additional connections to create under high load
# pool_pre_ping: Verify connections before use (prevents stale connection errors)
# pool_recycle: Recycle connections after specified seconds (prevents long-lived connection issues)
# echo_pool: Log pool checkouts/checkins for debugging (disabled in production)
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.debug,
    echo_pool=False,
    future=True
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True
)


def init_db() -> None:
    """
    Initialize database by creating all tables.

    This should be called on application startup or handled by migrations.
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to get database sessions.

    Yields:
        Database session

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db_session() as db:
            db.query(Asset).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        True if connection is successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
