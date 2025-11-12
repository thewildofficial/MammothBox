#!/usr/bin/env python3
"""
Database migration script
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.settings import get_settings
from sqlalchemy import create_engine, text

def run_migrations():
    """Run database migrations"""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    # Read and execute migration files
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')
    
    # TODO: Implement proper migration runner (Alembic)
    # For now, just ensure pgvector extension exists
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    
    print("Migrations completed")

if __name__ == "__main__":
    run_migrations()

