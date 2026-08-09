from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from data_utils import (
    BACKEND_DIR,
    DEFAULT_CATALOG_DIR,
    read_csv,
    resolve_catalog_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local SQLite product catalog.")
    parser.add_argument(
        "--input_csv", type=Path, default=DEFAULT_CATALOG_DIR / "articles_sample.csv"
    )
    parser.add_argument(
        "--db_path", type=Path, default=BACKEND_DIR / "data" / "sqlite" / "app.db"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = resolve_catalog_csv(args.input_csv)
    db_path = args.db_path.resolve()
    print(f"[1/4] Reading normalized catalog: {input_csv}", flush=True)
    _, rows = read_csv(input_csv)
    if not rows:
        raise RuntimeError("No catalog products found.")

    print(f"[2/4] Creating SQLite database: {db_path}", flush=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = db_path.with_name(db_path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE products (
                article_id TEXT PRIMARY KEY,
                product_code TEXT NOT NULL DEFAULT '',
                prod_name TEXT NOT NULL DEFAULT '',
                product_type_name TEXT NOT NULL DEFAULT '',
                product_group_name TEXT NOT NULL DEFAULT '',
                graphical_appearance_name TEXT NOT NULL DEFAULT '',
                colour_group_name TEXT NOT NULL DEFAULT '',
                perceived_colour_value_name TEXT NOT NULL DEFAULT '',
                perceived_colour_master_name TEXT NOT NULL DEFAULT '',
                department_name TEXT NOT NULL DEFAULT '',
                index_name TEXT NOT NULL DEFAULT '',
                index_group_name TEXT NOT NULL DEFAULT '',
                section_name TEXT NOT NULL DEFAULT '',
                garment_group_name TEXT NOT NULL DEFAULT '',
                detail_desc TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL,
                price REAL,
                popularity_score REAL NOT NULL DEFAULT 0,
                text_profile TEXT NOT NULL
            );
            CREATE INDEX idx_products_type ON products(product_type_name);
            CREATE INDEX idx_products_colour ON products(colour_group_name);
            CREATE INDEX idx_products_group ON products(product_group_name);
            """
        )
        columns = [
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
        ]
        placeholders = ",".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO products ({','.join(columns)}) VALUES ({placeholders})",
            [
                tuple(
                    (float(row[column]) if row.get(column) else None)
                    if column == "price"
                    else float(row.get(column) or 0)
                    if column == "popularity_score"
                    else row.get(column, "")
                    for column in columns
                )
                for row in rows
            ],
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    finally:
        connection.close()

    print("[3/4] Replacing previous database atomically", flush=True)
    temporary.replace(db_path)
    print("[4/4] Verifying products table", flush=True)
    if count != len(rows):
        raise RuntimeError(f"SQLite row count mismatch: {count} != {len(rows)}")
    print(f"SUCCESS: SQLite products rows={count:,}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
