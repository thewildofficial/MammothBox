#!/usr/bin/env python3
"""
Create a new database migration
"""

import sys
import os
from datetime import datetime

def create_migration(name: str):
    """Create a new migration file"""
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{name}.sql"
    filepath = os.path.join(migrations_dir, filename)
    
    content = f"""-- Migration: {name}
-- Created: {datetime.now().isoformat()}

-- TODO: Add your migration SQL here

"""
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"Created migration: {filepath}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_migration.py --name migration_name")
        sys.exit(1)
    
    name = sys.argv[2] if sys.argv[1] == "--name" else sys.argv[1]
    create_migration(name)

