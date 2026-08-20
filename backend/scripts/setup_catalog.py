"""One-time idempotent schema migration for the PostgreSQL product catalog."""

from __future__ import annotations

import os

import psycopg


def main() -> None:
    url = os.getenv("CATALOG_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("CATALOG_DATABASE_URL is required.")

    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
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
                    price DOUBLE PRECISION,
                    popularity_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                    text_profile TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_type ON products(product_type_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_colour ON products(colour_group_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group_name)"
            )
        connection.commit()
    print("catalog_schema=ready")


if __name__ == "__main__":
    main()
