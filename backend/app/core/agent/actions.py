from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


def _secret() -> bytes:
    value = os.getenv("AGENT_ACTION_SECRET") or os.getenv("AGENT_INTERNAL_TOKEN", "")
    if not value:
        raise RuntimeError("AGENT_ACTION_SECRET or AGENT_INTERNAL_TOKEN must be configured.")
    return value.encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_cart_confirmation(
    *, task_id: str, user_id: str, product: dict[str, Any], language: str
) -> dict[str, Any]:
    price = product.get("price")
    if not isinstance(price, (int, float)):
        raise ValueError("The selected product has no price for cart confirmation.")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    action_id = str(uuid4())
    image_url = str(product.get("image_url") or "")
    if not image_url:
        image_path = str(product.get("image_path") or "").replace("\\", "/")
        image_url = f"/media/{image_path.removeprefix('images/')}" if image_path else ""
    payload = {
        "action_id": action_id,
        "task_id": task_id,
        "user_id": user_id,
        "product_id": str(product["article_id"]),
        "product_name": str(product.get("prod_name") or product["article_id"]),
        "product_image_url": image_url,
        "expected_price": f"{float(price):.2f}",
        "quantity": 1,
        "exp": int(expires_at.timestamp()),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    product_name = payload["product_name"]
    return {
        "action_id": action_id,
        "action_type": "ADD_CART_ITEM",
        "summary": (
            f"Add {product_name} to your shopping bag"
            if language == "en"
            else f"将 {product_name} 加入购物车"
        ),
        "expires_at": expires_at.isoformat(),
        "confirmation_token": f"{encoded}.{signature}",
        "product": {
            "article_id": payload["product_id"],
            "prod_name": product_name,
            "price": float(price),
            "image_url": payload["product_image_url"],
        },
    }
