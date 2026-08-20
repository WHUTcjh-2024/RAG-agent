"""Helpers for PostgreSQL-backed integration tests.

The previous SQLite test suite relied on a writable on-disk file. After the
migration to PostgreSQL, these integration tests require a reachable database
for the store under test. When a connection URL is not configured the test is
skipped rather than failing, so ``pytest`` stays green in environments without a
running Postgres instance (the same way the SQLite suite needed a writable path).
"""

from __future__ import annotations

import os

import pytest


def require_postgres(env_var: str) -> None:
    """Skip the calling test when ``env_var`` does not name a PostgreSQL URL."""
    if not os.getenv(env_var, "").strip():
        pytest.skip(f"{env_var} is not configured; skipping PostgreSQL integration test.")
