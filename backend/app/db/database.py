from __future__ import annotations

from typing import Any

from app.core.catalog_fields import enrich_commerce_fields
from app.db.pg import connect as _pg_connect


def connect():
    """Open a PostgreSQL connection to the product catalog.

    Configure the catalog with ``CATALOG_DATABASE_URL`` (a ``postgresql://``
    connection string). There is no file-based fallback: a production catalog
    lives in PostgreSQL.
    """
    return _pg_connect("CATALOG_DATABASE_URL")


def catalog_ready() -> bool:
    """Best-effort liveness probe for the catalog database."""
    try:
        with connect() as connection:
            connection.execute("SELECT 1 FROM products LIMIT 1")
        return True
    except Exception:
        return False


def product_to_dict(row: Any) -> dict[str, Any]:
    product = dict(row)
    relative = str(product.get("image_path", "")).replace("\\", "/")
    product["image_url"] = (
        "/media/" + relative.removeprefix("images/") if relative else ""
    )
    return enrich_commerce_fields(product)
