from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from psycopg import Error as PgError

from app.db.database import connect, product_to_dict


router = APIRouter(tags=["products"])


@router.get("/products")
def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    category: str | None = Query(default=None),
    color: str | None = Query(default=None),
    group: str | None = Query(default=None),
    index_group: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    max_price: float | None = Query(default=None, ge=0),
    sort: str = Query(default="article_id", pattern="^(article_id|name|popular)$"),
) -> dict:
    clauses: list[str] = []
    parameters: list[object] = []
    if category:
        clauses.append("product_type_name ILIKE ?")
        parameters.append(f"%{category.strip()}%")
    if color:
        clauses.append("colour_group_name ILIKE ?")
        parameters.append(f"%{color.strip()}%")
    if group:
        clauses.append("product_group_name ILIKE ?")
        parameters.append(f"%{group.strip()}%")
    if index_group:
        clauses.append("index_group_name = ?")
        parameters.append(index_group.strip())
    if search:
        clauses.append("(prod_name ILIKE ? OR detail_desc ILIKE ?)")
        value = f"%{search.strip()}%"
        parameters.extend((value, value))
    if max_price is not None:
        clauses.append("price IS NOT NULL AND price <= ?")
        parameters.append(max_price)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    offset = (page - 1) * page_size
    try:
        with connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM products" + where, parameters
            ).fetchone()[0]
            order_by = {
                "article_id": "article_id",
                "name": "LOWER(prod_name), article_id",
                "popular": "popularity_score DESC, article_id",
            }[sort]
            rows = connection.execute(
                "SELECT * FROM products"
                + where
                + f" ORDER BY {order_by} LIMIT ? OFFSET ?",
                [*parameters, page_size, offset],
            ).fetchall()
    except (RuntimeError, PgError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [product_to_dict(row) for row in rows],
    }


@router.get("/products/facets")
def product_facets() -> dict:
    try:
        with connect() as connection:
            def values(column: str) -> list[str]:
                return [
                    row[0]
                    for row in connection.execute(
                        f"SELECT DISTINCT {column} FROM products "
                        f"WHERE {column} <> '' ORDER BY {column}"
                    ).fetchall()
                ]

            price = connection.execute(
                "SELECT MIN(price), MAX(price) FROM products WHERE price IS NOT NULL"
            ).fetchone()
            return {
                "categories": values("product_type_name"),
                "colors": values("colour_group_name"),
                "index_groups": values("index_group_name"),
                "price_range": [price[0], price[1]] if price[0] is not None else None,
            }
    except (RuntimeError, PgError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/products/{article_id}")
def get_product(article_id: str) -> dict:
    try:
        with connect() as connection:
            row = connection.execute(
                "SELECT * FROM products WHERE article_id = ?", (article_id,)
            ).fetchone()
    except (RuntimeError, PgError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product_to_dict(row)
