#!/usr/bin/env python3
"""
Run comprehensive stress tests and generate report.
"""

import sys
import os
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest


def main():
    """Run stress tests and generate report."""
    print("=" * 80)
    print("JOB QUEUE STRESS TESTS")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}\n")
    
    # Run pytest with verbose output
    exit_code = pytest.main([
        "tests/stress/test_queue_stress.py",
        "-v",
        "-s",  # Don't capture output
        "--tb=short",  # Short traceback format
        "-W", "ignore::DeprecationWarning"  # Ignore deprecation warnings
    ])
    
    print("\n" + "=" * 80)
    print(f"Completed at: {datetime.now().isoformat()}")
    print(f"Exit code: {exit_code}")
    print("=" * 80)
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

