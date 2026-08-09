from __future__ import annotations

import json
from typing import Any


def enrich_commerce_fields(product: dict[str, Any]) -> dict[str, Any]:
    """Expose honest commerce metadata for the normalized Tianchi catalog."""
    item = dict(product)
    item["sku"] = str(item.get("sku") or item.get("article_id") or "")
    raw_sizes = item.get("available_sizes")
    if isinstance(raw_sizes, str):
        try:
            parsed = json.loads(raw_sizes) if raw_sizes else []
            raw_sizes = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            raw_sizes = [value.strip() for value in raw_sizes.split(",") if value.strip()]
    item["available_sizes"] = raw_sizes if isinstance(raw_sizes, list) else []
    item["inventory_status"] = str(item.get("inventory_status") or "unknown")
    raw_price = item.get("price")
    try:
        amount = float(raw_price) if raw_price not in (None, "") else None
    except (TypeError, ValueError):
        amount = None
    item["price"] = amount
    item["price_info"] = (
        {
            "amount": amount,
            "currency": str(item.get("currency_code") or "CNY"),
            "source": str(item.get("price_source") or "tianchi_demo_price"),
        }
        if amount is not None
        else None
    )
    return item
