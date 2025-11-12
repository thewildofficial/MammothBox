#!/usr/bin/env python3
"""
Database migration script using Alembic.

Runs all pending database migrations to upgrade the schema.
"""

from src.config.settings import get_settings
from alembic import command
from alembic.config import Config
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_migrations():
    """Run database migrations using Alembic."""

    settings = get_settings()

    # Configure Alembic
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(project_root / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    print("Running database migrations...")
    try:
        # Upgrade to the latest migration
        command.upgrade(alembic_cfg, "head")
        print("✓ Migrations completed successfully")
    except Exception as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


def downgrade_migrations(revision: str = "-1"):
    """
    Downgrade database migrations.

    Args:
        revision: Target revision to downgrade to (default: -1 for previous version)
    """
    settings = get_settings()

    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(project_root / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    print(f"Downgrading database to revision: {revision}...")
    try:
        command.downgrade(alembic_cfg, revision)
        print("✓ Downgrade completed successfully")
    except Exception as e:
        print(f"✗ Downgrade failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
        downgrade_migrations(revision)
    else:
        run_migrations()
