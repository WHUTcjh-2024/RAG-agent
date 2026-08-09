from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from app.core.catalog_fields import enrich_commerce_fields
from app.core.catalog_paths import DEFAULT_SQLITE_PATH, get_catalog_dir


def get_db_path() -> Path:
    configured = os.getenv("CATALOG_DB_PATH", "").strip() or os.getenv(
        "SQLITE_PATH", ""
    ).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    catalog_db = get_catalog_dir() / "app.db"
    return catalog_db.resolve() if catalog_db.is_file() else DEFAULT_SQLITE_PATH


def connect() -> sqlite3.Connection:
    path = get_db_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"SQLite catalog not found: {path}. Run backend\\scripts\\build_sqlite.py."
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def product_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    product = dict(row)
    relative = str(product.get("image_path", "")).replace("\\", "/")
    product["image_url"] = (
        "/media/" + relative.removeprefix("images/") if relative else ""
    )
    return enrich_commerce_fields(product)
