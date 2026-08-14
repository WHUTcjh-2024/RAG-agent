from __future__ import annotations

# ruff: noqa: E402

import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException
from app.core.agent.skills import AgentSkill, ShoppingSkillRegistry
from tests.test_agent_workflow import create_workflow, invoke_recommendation


def test_skill_registry_declares_tool_boundaries() -> None:
    retrieval = ShoppingSkillRegistry.resolve(
        intent="text_recommendation", decision_product_id=None
    )
    handoff = ShoppingSkillRegistry.resolve(
        intent="cart_handoff", decision_product_id=None
    )

    assert retrieval.id == "catalog_retrieval"
    assert ShoppingSkillRegistry.permits(retrieval, "search_products_by_text")
    assert ShoppingSkillRegistry.permits(retrieval, "get_product_detail")
    assert ShoppingSkillRegistry.permits(retrieval, "compare_products")
    assert handoff.risk_level == "confirm_required"


def test_runtime_guard_rejects_tool_outside_current_skill(tmp_path: Path) -> None:
    workflow, orchestrator = create_workflow(tmp_path)
    skill = AgentSkill(
        id="restricted_catalog",
        version="v1",
        description="Test-only restricted catalog access.",
        risk_level="read_only",
        allowed_tools=["search_products_by_text"],
        supported_intents=["text_recommendation"],
    )
    try:
        with pytest.raises(AgentException) as denied:
            orchestrator._invoke(
                [],
                "get_product_detail",
                {"product_id": "0000000001"},
                skill=skill,
            )
    finally:
        workflow.close()

    assert denied.value.code == ErrorCode.TOOL_NOT_PERMITTED
    assert denied.value.status_code == 403
    assert denied.value.stage == "invoke_tool"
    assert denied.value.details == {
        "tool": "get_product_detail",
        "skill_id": "restricted_catalog",
        "skill_version": "v1",
    }


def test_completed_task_has_versioned_skill_and_safe_replay(tmp_path: Path) -> None:
    workflow, _ = create_workflow(tmp_path)
    try:
        response = invoke_recommendation(workflow, "harness-replay")
        replay = workflow.get_replay(
            task_id="harness-replay",
            session_id="workflow-session",
            trusted_user_id=None,
        )
    finally:
        workflow.close()

    assert response.skill is not None
    assert response.skill.id == "catalog_retrieval"
    assert replay["skill"] == response.skill.model_dump(mode="json")
    assert replay["nodes"] == [
        trace.model_dump(mode="json") for trace in response.node_trace
    ]
    assert replay["tools"] == [
        trace.model_dump(mode="json") for trace in response.tool_trace
    ]
    assert "message" not in replay
    assert "answer" not in replay


def test_replay_requires_matching_session(tmp_path: Path) -> None:
    workflow, _ = create_workflow(tmp_path)
    try:
        invoke_recommendation(workflow, "harness-session")
        try:
            workflow.get_replay(
                task_id="harness-session",
                session_id="another-session",
                trusted_user_id=None,
            )
        except Exception as error:
            assert getattr(error, "status_code", None) == 404
        else:  # pragma: no cover - protects the ownership check
            raise AssertionError("Expected replay ownership validation to fail")
    finally:
        workflow.close()
