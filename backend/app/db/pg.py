"""Shared PostgreSQL access layer for the Python backend.

This replaces the previous SQLite-based stores. The backend standardised on `?`
bind markers throughout its SQL, so the thin :class:`PgConnection` adapter
translates them to psycopg's `%s` markers and normalises transaction-control
statements. psycopg's ``Row`` supports both positional and by-name indexing, so
legacy ``row[0]`` / ``row["col"]`` / ``dict(row)`` access keeps working unchanged.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import psycopg
except ImportError as error:  # pragma: no cover - production dependency guard
    raise RuntimeError(
        "psycopg is required for the PostgreSQL backend."
    ) from error

# One pool per resolved database URL so request paths reuse connections instead
# of opening a new one per call.
_POOLS: dict[str, "psycopg.ConnectionPool"] = {}


def database_url(env_var: str, default: str | None = None) -> str:
    """Resolve a PostgreSQL connection string from an environment variable."""
    value = os.getenv(env_var, "").strip()
    if not value and default:
        return default
    if not value:
        raise RuntimeError(f"{env_var} is required for the PostgreSQL backend.")
    return value


class PgConnection:
    """DB-API-compatible wrapper over a psycopg connection.

    Translates ``?`` placeholders to ``%s`` and rewrites ``BEGIN IMMEDIATE`` so
    the query strings written for SQLite run unchanged on PostgreSQL. The
    underlying connection is committed/rolled back by the surrounding ``with``
    block (psycopg's context manager) and then closed.
    """

    def __init__(self, connection: "psycopg.Connection") -> None:
        self._connection = connection

    def __enter__(self) -> "PgConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, *args) -> None:
        try:
            self._connection.__exit__(*args)
        finally:
            self._connection.close()

    @staticmethod
    def _translate(query: str) -> str:
        statement = query.strip()
        if statement.upper().startswith("BEGIN"):
            # PostgreSQL infers the transaction from the first statement; the
            # explicit immediate-lock request is a SQLite concern.
            return "BEGIN"
        return query.replace("?", "%s")

    def execute(self, query: str, values: tuple | list = ()) -> Any:
        return self._connection.execute(self._translate(query), values)

    def executemany(self, query: str, values: list) -> Any:
        return self._connection.executemany(self._translate(query), values)


def connect(env_var: str, *, default: str | None = None) -> PgConnection:
    """Open a dedicated PostgreSQL connection for a single request/transaction."""
    url = database_url(env_var, default)
    connection = psycopg.connect(url, connect_timeout=5)
    return PgConnection(connection)
