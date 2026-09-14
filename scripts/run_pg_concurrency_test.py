"""
Standalone PostgreSQL Concurrency Test Runner

Usage:
    python scripts/run_pg_concurrency_test.py [postgresql_connection_string]

If no connection string is provided as a CLI argument, reads from
TEST_DATABASE_URL or POSTGRES_DATABASE_URL environment variable.
"""

import sys
import os
import concurrent.futures

def run_tests(pg_url: str):
    print(f"[*] Running PostgreSQL concurrency test against: {pg_url}")
    os.environ["TEST_DATABASE_URL"] = pg_url

    import pytest
    exit_code = pytest.main([
        "-v",
        "tests/test_concurrency_pg.py"
    ])
    if exit_code == 0:
        print("[OK] PostgreSQL concurrency tests PASSED.")
    else:
        print(f"[FAIL] PostgreSQL concurrency tests failed with exit code {exit_code}.")
    return exit_code

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.getenv("TEST_DATABASE_URL") or os.getenv("POSTGRES_DATABASE_URL")

    if not url:
        print("[-] Error: No PostgreSQL URL provided.")
        print("Usage: python scripts/run_pg_concurrency_test.py postgresql://user:pass@host:5432/dbname")
        print("Or set TEST_DATABASE_URL in environment.")
        sys.exit(1)

    sys.exit(run_tests(url))
