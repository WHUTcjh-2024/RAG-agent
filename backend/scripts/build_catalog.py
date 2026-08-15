"""Seed the PostgreSQL product catalog from the normalized Tianchi CSV."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

from data_utils import (
    BACKEND_DIR,
    DEFAULT_CATALOG_DIR,
    read_csv,
    resolve_catalog_csv,
)

PRODUCT_COLUMNS = (
    "article_id",
    "product_code",
    "prod_name",
    "product_type_name",
    "product_group_name",
    "graphical_appearance_name",
    "colour_group_name",
    "perceived_colour_value_name",
    "perceived_colour_master_name",
    "department_name",
    "index_name",
    "index_group_name",
    "section_name",
    "garment_group_name",
    "detail_desc",
    "image_path",
    "price",
    "popularity_score",
    "text_profile",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the PostgreSQL product catalog.")
    parser.add_argument(
        "--input_csv", type=Path, default=DEFAULT_CATALOG_DIR / "articles_sample.csv"
    )
    return parser.parse_args()


def _row_values(row: dict[str, str]) -> tuple[object, ...]:
    return tuple(
        (float(row[column]) if row.get(column) else None)
        if column == "price"
        else float(row.get(column) or 0)
        if column == "popularity_score"
        else row.get(column, "")
        for column in PRODUCT_COLUMNS
    )


def main() -> int:
    args = parse_args()
    input_csv = resolve_catalog_csv(args.input_csv)
    _, rows = read_csv(input_csv)
    if not rows:
        raise RuntimeError("No catalog products found.")

    url = os.getenv("CATALOG_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("CATALOG_DATABASE_URL is required.")

    placeholders = ",".join("%s" for _ in PRODUCT_COLUMNS)
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE products")
            cursor.executemany(
                f"INSERT INTO products ({','.join(PRODUCT_COLUMNS)}) VALUES ({placeholders})",
                [_row_values(row) for row in rows],
            )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    if count != len(rows):
        raise RuntimeError(f"PostgreSQL row count mismatch: {count} != {len(rows)}")
    print(f"SUCCESS: PostgreSQL products rows={count:,}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, psycopg.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
