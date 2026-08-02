from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.agent.errors import AgentException
from app.core.agent.wardrobe import WardrobeItem, WardrobePlanner, WardrobeSnapshot


def snapshot(version: int = 4) -> WardrobeSnapshot:
    return WardrobeSnapshot(
        version=version,
        observed_at=datetime.now(timezone.utc),
        items=[
            WardrobeItem("shirt-1", None, "White shirt", "Shirt", "White", None),
            WardrobeItem("shoes-1", None, "Black shoes", "Shoes", "Black", None),
        ],
    )


def candidates() -> list[dict]:
    return [
        {"article_id": "top-2", "prod_name": "Blue shirt", "product_type_name": "Shirt", "price": 40},
        {"article_id": "bottom-1", "prod_name": "Tailored trousers", "product_type_name": "Trousers", "price": 50},
        {"article_id": "bottom-2", "prod_name": "Navy trousers", "product_type_name": "Trousers", "price": 60},
    ]


def test_plan_reuses_wardrobe_and_only_adds_missing_categories() -> None:
    planner = WardrobePlanner()
    plan = planner.create_plan(
        snapshot=snapshot(),
        slots={"outfit_count": 2, "budget": 180, "scenario": "interview"},
        candidates=candidates(),
    )

    assert planner.missing_categories(snapshot(), {"outfit_count": 2}) == ["TOP", "BOTTOM", "BOTTOM"]
    assert len(plan["outfits"]) == 2
    assert plan["outfits"][0]["items"][0]["source"] == "WARDROBE"
    assert all(outfit["complete"] for outfit in plan["outfits"])
    assert plan["new_item_total"] == 150
    assert plan["missing_categories"] == []


def test_local_replan_rejects_stale_wardrobe_and_preserves_other_outfits() -> None:
    planner = WardrobePlanner()
    plan = planner.create_plan(snapshot=snapshot(), slots={"outfit_count": 2}, candidates=candidates())
    first = plan["outfits"][0]
    edited = planner.replan(
        plan=plan,
        snapshot=snapshot(),
        operation={"action": "LOCK", "outfit_id": first["outfit_id"], "item_id": first["items"][0]["item_id"]},
    )
    assert edited["outfits"][0]["items"][0]["locked"] is True
    assert edited["outfits"][1] == plan["outfits"][1]

    with pytest.raises(AgentException, match="Wardrobe changed"):
        planner.replan(
            plan=plan,
            snapshot=snapshot(version=5),
            operation={"action": "LOCK", "outfit_id": first["outfit_id"], "item_id": first["items"][0]["item_id"]},
        )
