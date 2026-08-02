from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException, invalid_input
from app.core.agent.resilience import CircuitBreaker


REQUIRED_CATEGORIES = ("TOP", "BOTTOM")


@dataclass(frozen=True)
class WardrobeItem:
    id: str
    source_product_id: str | None
    name: str
    category: str
    color: str | None
    image_url: str | None


@dataclass(frozen=True)
class WardrobeSnapshot:
    version: int
    items: list[WardrobeItem]
    observed_at: datetime


class WardrobeProvider(Protocol):
    def get(self, *, user_id: str) -> WardrobeSnapshot: ...


class JavaWardrobeProvider:
    """Reads the versioned wardrobe snapshot from Java; never falls back to local data."""

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 2) -> None:
        self.base_url = (base_url or os.getenv("AGENT_FACTS_BASE_URL", "")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._breaker = CircuitBreaker("load_wardrobe")

    def get(self, *, user_id: str) -> WardrobeSnapshot:
        if not self.base_url:
            raise AgentException(
                ErrorCode.BUSINESS_FACT_UNAVAILABLE,
                "Java wardrobe facts are not configured.",
                status_code=503,
                retryable=True,
                stage="load_wardrobe",
            )
        token = os.getenv("AGENT_FACTS_INTERNAL_TOKEN", "")
        request = Request(
            f"{self.base_url}/internal/agent/wardrobe?{urlencode({'trusted_user_id': user_id})}",
            headers={"X-Agent-Internal-Token": token},
        )
        try:
            def load() -> dict[str, Any]:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                    return json.loads(response.read().decode("utf-8"))

            payload = self._breaker.call(load)
        except Exception as error:
            if isinstance(error, AgentException) and error.code == ErrorCode.UPSTREAM_UNAVAILABLE:
                raise
            raise AgentException(
                ErrorCode.BUSINESS_FACT_UNAVAILABLE,
                "Java wardrobe facts are temporarily unavailable.",
                status_code=503,
                retryable=True,
                stage="load_wardrobe",
            ) from error
        observed_at = payload.get("observedAt") or payload.get("observed_at")
        return WardrobeSnapshot(
            version=int(payload.get("version", 0)),
            items=[
                WardrobeItem(
                    id=str(item["id"]),
                    source_product_id=item.get("sourceProductId") or item.get("source_product_id"),
                    name=str(item["name"]),
                    category=str(item["category"]),
                    color=item.get("color"),
                    image_url=item.get("imageUrl") or item.get("image_url"),
                )
                for item in payload.get("items", [])
            ],
            observed_at=datetime.fromisoformat(
                (observed_at or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
        )


def canonical_category(value: str | None) -> str:
    folded = (value or "").casefold()
    if any(term in folded for term in ("shirt", "top", "sweater", "t-shirt", "tee", "衬衫", "上衣", "毛衣")):
        return "TOP"
    if any(term in folded for term in ("trouser", "pants", "bottom", "skirt", "shorts", "裤", "裙")):
        return "BOTTOM"
    if any(term in folded for term in ("jacket", "coat", "outer", "外套", "夹克")):
        return "OUTERWEAR"
    if any(term in folded for term in ("shoe", "boot", "鞋")):
        return "SHOES"
    return "OTHER"


class WardrobePlanner:
    """Deterministic planner: catalogue data proposes purchases, Java wardrobe data is authoritative."""

    @staticmethod
    def outfit_count(slots: dict[str, Any]) -> int:
        raw = slots.get("outfit_count", 1)
        try:
            return max(1, min(int(raw), 5))
        except (TypeError, ValueError):
            return 1

    def missing_categories(self, snapshot: WardrobeSnapshot, slots: dict[str, Any]) -> list[str]:
        count = self.outfit_count(slots)
        available = defaultdict(int)
        for item in snapshot.items:
            available[canonical_category(item.category)] += 1
        return [
            category
            for category in REQUIRED_CATEGORIES
            for _ in range(max(0, count - available[category]))
        ]

    def create_plan(
        self,
        *,
        snapshot: WardrobeSnapshot,
        slots: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        count = self.outfit_count(slots)
        budget = self._number(slots.get("budget"))
        wardrobe_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in snapshot.items:
            wardrobe_by_category[canonical_category(item.category)].append(
                {
                    "item_id": item.id,
                    "source": "WARDROBE",
                    "name": item.name,
                    "category": canonical_category(item.category),
                    "image_url": item.image_url,
                    "locked": False,
                }
            )
        catalog_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for product in candidates:
            category = canonical_category(str(product.get("product_type_name") or product.get("product_group_name") or ""))
            if category in REQUIRED_CATEGORIES:
                catalog_by_category[category].append(product)

        used_catalog: set[str] = set()
        outfits: list[dict[str, Any]] = []
        unresolved: list[str] = []
        total_new_cost = 0.0
        for index in range(count):
            items: list[dict[str, Any]] = []
            for category in REQUIRED_CATEGORIES:
                existing = self._at(wardrobe_by_category[category], index)
                if existing:
                    items.append(dict(existing))
                    continue
                product = self._next_catalog(catalog_by_category[category], used_catalog)
                if not product:
                    unresolved.append(category)
                    continue
                price = self._number(product.get("price"))
                if budget is not None and price is not None and total_new_cost + price > budget:
                    unresolved.append(category)
                    continue
                product_id = str(product.get("article_id"))
                used_catalog.add(product_id)
                total_new_cost += price or 0
                items.append(
                    {
                        "item_id": product_id,
                        "source": "CATALOG",
                        "name": str(product.get("prod_name") or product_id),
                        "category": category,
                        "image_url": product.get("image_url"),
                        "price": price,
                        "locked": False,
                    }
                )
            outfits.append(
                {
                    "outfit_id": f"outfit-{index + 1}",
                    "name": f"Option {index + 1}",
                    "items": items,
                    "complete": len(items) == len(REQUIRED_CATEGORIES),
                }
            )
        missing = list(dict.fromkeys(unresolved))
        return {
            "plan_id": f"wardrobe-{uuid4().hex}",
            "wardrobe_version": snapshot.version,
            "snapshot_summary": {"item_count": len(snapshot.items), "observed_at": snapshot.observed_at.isoformat()},
            "constraints": {"budget": budget, "outfit_count": count, "scenario": slots.get("scenario"), "date": slots.get("date"), "weather": slots.get("weather")},
            "outfits": outfits,
            "missing_categories": missing,
            "new_item_total": round(total_new_cost, 2),
            "fallback": "Reuse the complete outfit and relax the requested outfit count." if missing else None,
        }

    def replan(
        self,
        *,
        plan: dict[str, Any],
        snapshot: WardrobeSnapshot,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        if int(plan.get("wardrobe_version", -1)) != snapshot.version:
            raise invalid_input("Wardrobe changed; refresh the plan before editing.", status_code=409)
        outfit_id = str(operation.get("outfit_id") or "")
        action = str(operation.get("action") or "")
        outfits = [dict(outfit) for outfit in plan.get("outfits", [])]
        target = next((outfit for outfit in outfits if outfit.get("outfit_id") == outfit_id), None)
        if target is None or action not in {"LOCK", "REMOVE", "REPLACE"}:
            raise invalid_input("Plan edit is invalid.")
        items = [dict(item) for item in target.get("items", [])]
        item_id = str(operation.get("item_id") or "")
        position = next((index for index, item in enumerate(items) if item.get("item_id") == item_id), None)
        if position is None:
            raise invalid_input("Plan item was not found.", status_code=404)
        if action == "LOCK":
            items[position]["locked"] = not bool(items[position].get("locked"))
        elif action == "REMOVE":
            if items[position].get("locked"):
                raise invalid_input("Unlock the item before removing it.", status_code=409)
            items.pop(position)
        else:
            replacement = operation.get("replacement")
            if not isinstance(replacement, dict) or items[position].get("locked"):
                raise invalid_input("Replacement is invalid or the item is locked.", status_code=409)
            if canonical_category(str(replacement.get("category") or "")) != items[position].get("category"):
                raise invalid_input("Replacement category does not match the outfit slot.")
            items[position] = {
                "item_id": str(replacement.get("item_id") or ""),
                "source": str(replacement.get("source") or "CATALOG"),
                "name": str(replacement.get("name") or ""),
                "category": items[position]["category"],
                "image_url": replacement.get("image_url"),
                "price": self._number(replacement.get("price")),
                "locked": False,
            }
        target["items"] = items
        target["complete"] = len(items) == len(REQUIRED_CATEGORIES)
        result = dict(plan)
        result["outfits"] = outfits
        result["replan_scope"] = {"outfit_id": outfit_id, "action": action}
        return result

    @staticmethod
    def _at(values: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
        return values[index] if index < len(values) else None

    @staticmethod
    def _next_catalog(values: list[dict[str, Any]], used: set[str]) -> dict[str, Any] | None:
        return next((value for value in values if str(value.get("article_id")) not in used), None)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
