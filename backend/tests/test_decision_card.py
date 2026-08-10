from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.agent.decision import (
    DecisionCardBuilder,
    DecisionFacts,
    DecisionVerdict,
)
from tests.test_agent_workflow import create_workflow


def facts(**overrides) -> DecisionFacts:
    observed_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    product_source = {
        "source_kind": "MERCHANT_FEED",
        "source_id": "merchant:catalog-1",
        "source_label": "商家商品数据",
        "observed_at": observed_at,
        "confidence": 0.95,
        "verified": True,
    }
    values = {
        "user_id": "user-1",
        "product_id": "0000000001",
        "sku_id": "sku-1-m",
        "profile": {"chest_cm": 96},
        "sku_measurements": {"chest_cm": 104, "size": "M"},
        "price": {"amount": 299},
        "inventory": {"in_stock": True},
        "return_policy": {"summary": "支持七天无理由退换"},
        "version": "facts-v1",
        "observed_at": observed_at,
        "provenance": {
            "bodyProfile.chestCm": {
                "source_kind": "USER_DECLARED",
                "source_id": "body-profile:user-1",
                "source_label": "用户填写的身体档案",
                "observed_at": observed_at,
                "confidence": 0.70,
                "verified": True,
            },
            "skuMeasurement.chestCm": product_source,
            "skuMeasurement.size": product_source,
            "price.amount": product_source,
            "inventory.inStock": product_source,
            "returnPolicy.summary": product_source,
        },
    }
    values.update(overrides)
    return DecisionFacts(**values)


@pytest.mark.parametrize(
    ("input_facts", "verdict"),
    [
        (facts(), DecisionVerdict.RECOMMEND_BUY),
        (facts(sku_measurements={"chest_cm": 100, "size": "M"}), DecisionVerdict.BUY_WITH_CAUTION),
        (facts(sku_measurements={"chest_cm": 94, "size": "M"}), DecisionVerdict.NOT_RECOMMENDED),
        (facts(sku_measurements={}), DecisionVerdict.INSUFFICIENT_DATA),
    ],
)
def test_decision_card_covers_all_documented_verdicts(input_facts, verdict) -> None:
    card = DecisionCardBuilder().build(facts=input_facts, alternatives=[])

    assert card.verdict == verdict
    if verdict == DecisionVerdict.INSUFFICIENT_DATA:
        assert card.recommended_size is None
        assert card.confidence == 0
        assert "skuMeasurement.chestCm" in card.missing_fields
    else:
        assert card.evidence
        assert card.confidence_components["rule"] > 0
        assert card.confidence_components["model"] == 0
    if card.recommended_size:
        assert any(item.field == "size" for item in card.evidence)
    for risk in card.fit_risks:
        assert risk.evidence_refs


def test_missing_java_facts_never_invents_a_precise_size() -> None:
    card = DecisionCardBuilder().build(facts=None, alternatives=[])

    assert card.verdict == DecisionVerdict.INSUFFICIENT_DATA
    assert card.recommended_size is None
    assert card.evidence == []
    assert "trustedBodyProfile" in card.missing_fields
    assert card.verification.status.value == "BLOCKED"
    assert card.fact_passport.status.value == "INCOMPLETE"


def test_unverified_critical_fact_blocks_a_purchase_decision() -> None:
    source_data = facts()
    provenance = dict(source_data.provenance)
    provenance["price.amount"] = {
        **provenance["price.amount"],
        "verified": False,
        "source_kind": "OCR_CANDIDATE",
    }

    card = DecisionCardBuilder().build(
        facts=facts(provenance=provenance), alternatives=[]
    )

    assert card.verdict == DecisionVerdict.INSUFFICIENT_DATA
    assert "price.amount.provenance" in card.missing_fields
    assert card.verification.status.value == "BLOCKED"


def test_budget_violation_is_rejected_by_the_independent_verifier() -> None:
    card = DecisionCardBuilder().build(facts=facts(), alternatives=[], budget=199)

    assert card.verdict == DecisionVerdict.NOT_RECOMMENDED
    assert card.verification.status.value == "REJECTED"
    assert any(
        check.code == "budget" and check.status.value == "FAIL"
        for check in card.verification.checks
    )


def test_return_policy_is_a_required_purchase_fact() -> None:
    card = DecisionCardBuilder().build(
        facts=facts(return_policy={}), alternatives=[]
    )

    assert card.verdict == DecisionVerdict.INSUFFICIENT_DATA
    assert "returnPolicy.summary" in card.missing_fields


class StaticFactsProvider:
    def get(self, *, user_id: str, product_id: str) -> DecisionFacts:
        return facts(user_id=user_id, product_id=product_id)


def test_workflow_emits_a_grounded_decision_without_an_llm(tmp_path) -> None:
    workflow, orchestrator = create_workflow(tmp_path)
    orchestrator.decision_facts_provider = StaticFactsProvider()
    try:
        response = workflow.invoke(
            task_id="decision-card-task",
            message="请判断这件商品是否合适",
            session_id="decision-session",
            trusted_user_id="trusted-user-1",
            decision_product_id="0000000001",
        )
    finally:
        workflow.close()

    assert response.decision is not None
    assert response.decision.verdict == DecisionVerdict.RECOMMEND_BUY
    assert response.decision.recommended_size == "M"
    assert response.decision.evidence[0].source_type.value == "BODY_PROFILE"
