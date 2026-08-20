from __future__ import annotations

# ruff: noqa: E402

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import pytest
import psycopg
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.chat import get_memory, get_orchestrator, reset_workflow
from app.core.agent.errors import AgentException
from app.core.agent.memory import AgentMemoryStore
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.workflow import (
    RecoverableShoppingAgentWorkflow,
    validate_task_id,
)
from app.core.llm import GroundedRecommendationGenerator
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever
from app.core.agent.wardrobe import WardrobeItem, WardrobeSnapshot
from app.main import app
from tests.postgres_helpers import require_postgres
from tests.test_hybrid_retrieval import build_fixture_indexes


def _truncate_existing_tables(connection: psycopg.Connection, tables: tuple[str, ...]) -> None:
    existing = [
        table
        for table in tables
        if connection.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0]
    ]
    if existing:
        connection.execute(f"TRUNCATE TABLE {', '.join(existing)} CASCADE")


@pytest.fixture(autouse=True)
def isolate_postgres_workflow_state() -> None:
    """Keep fixed workflow fixtures independent when CI shares PostgreSQL."""
    memory_url = os.environ.get("AGENT_MEMORY_DATABASE_URL")
    checkpoint_url = os.environ.get("AGENT_CHECKPOINT_DATABASE_URL")
    if not memory_url or not checkpoint_url:
        yield
        return

    with psycopg.connect(memory_url, connect_timeout=5) as connection:
        _truncate_existing_tables(
            connection,
            ("agent_actions", "agent_task_controls", "agent_task_commits", "agent_sessions"),
        )
    with psycopg.connect(checkpoint_url, connect_timeout=5) as connection:
        _truncate_existing_tables(
            connection,
            ("checkpoint_writes", "checkpoint_blobs", "checkpoints"),
        )
    yield


def create_workflow(
    root: Path,
    *,
    reason_generator: GroundedRecommendationGenerator | None = None,
) -> tuple[RecoverableShoppingAgentWorkflow, ShoppingAgentOrchestrator]:
    # The PostgreSQL-backed stores read their connection URL from the
    # environment; without one there is nothing to test against.
    require_postgres("AGENT_MEMORY_DATABASE_URL")
    require_postgres("AGENT_CHECKPOINT_DATABASE_URL")
    # Self-initialise the schema the way the deploy-time migrations would, so
    # the tests are self-contained against a fresh database.
    os.environ["AGENT_MEMORY_AUTO_SETUP"] = "true"
    os.environ["AGENT_CHECKPOINT_AUTO_SETUP"] = "true"
    text_index, image_index, _ = build_fixture_indexes(root / "indexes")
    orchestrator = ShoppingAgentOrchestrator(
        text_retriever=TextRetriever(text_index),
        image_retriever=ImageRetriever(image_index, device="cpu"),
        hybrid_retriever=HybridRetriever(
            text_index,
            image_index,
            image_device="cpu",
        ),
        memory=AgentMemoryStore(),
        reason_generator=reason_generator,
    )
    workflow = RecoverableShoppingAgentWorkflow(orchestrator)
    return workflow, orchestrator


def invoke_recommendation(
    workflow: RecoverableShoppingAgentWorkflow,
    task_id: str,
    *,
    request_id: str = "workflow-request",
):
    return workflow.invoke(
        task_id=task_id,
        message="推荐一件红色衬衫",
        session_id="workflow-session",
        request_id=request_id,
    )


def test_recommendation_executes_documented_nodes_and_persists_state(
    tmp_path: Path,
) -> None:
    workflow, _ = create_workflow(tmp_path)
    try:
        response = invoke_recommendation(workflow, "documented-nodes")
        state = workflow.get_task_state("documented-nodes")
    finally:
        workflow.close()

    assert state["executed_nodes"] == [
        "validate_input",
        "understand_request",
        "load_context",
        "plan_tools",
        "retrieve_candidates",
        "observe_and_replan",
        "verify_constraints",
        "build_evidence",
        "generate_answer",
        "complete",
    ]
    assert [trace.node for trace in response.node_trace] == state["executed_nodes"]
    assert all(trace.duration_ms >= 0 for trace in response.node_trace)
    assert state["hard_constraints"] == {
        "color": "Red",
        "category": "Shirt",
    }
    assert state["context_refs"]["candidate_article_ids"] == ["0000000001"]
    assert state["evidence"][0]["source"] == "catalog"
    assert state["status"] == "completed"
    assert state["react_observations"][0]["tool"] == "search_products_by_text"
    assert state["react_stop_reason"] == "sufficient_evidence"

    checkpoint_url = os.environ["AGENT_CHECKPOINT_DATABASE_URL"]
    with psycopg.connect(checkpoint_url, connect_timeout=5) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        }
    # LangGraph's PostgresSaver creates these two tables for checkpoints and
    # the per-write payloads.
    assert {"checkpoints", "checkpoint_writes"} <= tables


def test_react_loop_replans_after_empty_search_and_stops_at_evidence(
    tmp_path: Path,
) -> None:
    workflow, orchestrator = create_workflow(tmp_path)
    original_invoke = orchestrator.registry.invoke
    searches = 0

    def empty_then_results(name, arguments):
        nonlocal searches
        if name == "search_products_by_text":
            searches += 1
            if searches == 1:
                return {"results": [], "total_candidates": 0}
        return original_invoke(name, arguments)

    orchestrator.registry.invoke = empty_then_results
    try:
        response = invoke_recommendation(workflow, "react-replan")
        state = workflow.get_task_state("react-replan")
    finally:
        workflow.close()

    assert searches == 2
    assert len(state["react_observations"]) == 2
    assert state["react_stop_reason"] == "sufficient_evidence"
    assert state["executed_nodes"].count("retrieve_candidates") == 2
    assert state["executed_nodes"].count("observe_and_replan") == 2
    assert len(response.tool_trace) == 2


def test_react_loop_allows_model_to_inspect_observed_product_detail(
    tmp_path: Path,
) -> None:
    workflow, orchestrator = create_workflow(tmp_path)

    class DetailAfterSearch:
        def replan(self, **kwargs):
            observations = kwargs["observations"]
            if len(observations) == 1:
                return SimpleNamespace(
                    action="tool",
                    tool="get_product_detail",
                    query=None,
                    product_ids=observations[0]["product_ids"][:1],
                )
            return SimpleNamespace(action="finish", tool=None, query=None, product_ids=[])

    orchestrator.planner.replan = DetailAfterSearch().replan
    try:
        response = invoke_recommendation(workflow, "react-product-detail")
        state = workflow.get_task_state("react-product-detail")
    finally:
        workflow.close()

    assert [trace.tool for trace in response.tool_trace] == [
        "search_products_by_text",
        "get_product_detail",
    ]
    assert state["react_stop_reason"] == "sufficient_evidence"


def test_workflow_streams_only_verified_rendering_not_provider_tokens(
    tmp_path: Path,
) -> None:
    generator = GroundedRecommendationGenerator(chain=None)
    workflow, _ = create_workflow(tmp_path, reason_generator=generator)
    try:
        events = list(
            workflow.stream(
                task_id="verified-token-stream",
                message="recommend a red shirt",
                session_id="stream-session",
                request_id="stream-request",
            )
        )
    finally:
        workflow.close()

    tokens = [event["data"]["token"] for event in events if event["type"] == "token"]
    result_index = next(index for index, event in enumerate(events) if event["type"] == "result")
    answer = "".join(tokens)
    assert answer == "根据你的需求，我从真实商品库中筛出了这些候选。"
    assert "99" not in answer
    assert "羊毛" not in answer
    assert all(index < result_index for index, event in enumerate(events) if event["type"] == "token")
    assert events[result_index]["response"]["answer"] == answer


def test_cart_route_runs_confirmation_node_without_python_cart_tool(
    tmp_path: Path,
) -> None:
    workflow, _ = create_workflow(tmp_path)
    try:
        response = workflow.invoke(
            task_id="cart-route",
            message="把第一件加入购物车",
            session_id="cart-session",
            request_id="cart-request",
        )
        state = workflow.get_task_state("cart-route")
    finally:
        workflow.close()

    assert "wait_for_confirmation" in state["executed_nodes"]
    assert response.intent == "cart_handoff"
    assert "登录" in response.answer
    assert response.tool_trace == []
    assert workflow.route_after_answer({"pending_action": {"type": "handoff"}}) == (
        "wait_for_confirmation"
    )
    assert workflow.route_after_answer({"pending_action": None}) == "complete"


def test_authenticated_cart_route_returns_confirmation_without_writing_cart(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENT_ACTION_SECRET", "workflow-action-secret")
    workflow, orchestrator = create_workflow(tmp_path)
    orchestrator.memory.set_last_results("cart-session", ["0000000001"])
    try:
        response = workflow.invoke(
            task_id="authenticated-cart-route",
            message="把第1件加入购物车",
            session_id="cart-session",
            request_id="cart-request",
            trusted_user_id="trusted-user",
        )
    finally:
        workflow.close()

    assert response.pending_action is not None
    assert response.pending_action["action_type"] == "ADD_CART_ITEM"
    assert response.pending_action["product"]["article_id"] == "0000000001"
    assert response.pending_action["confirmation_token"].count(".") == 1
    assert response.tool_trace[0].tool == "get_product_detail"


def test_wardrobe_task_uses_versioned_context_and_only_searches_missing_categories(
    tmp_path: Path,
) -> None:
    class FixtureWardrobe:
        def get(self, *, user_id: str) -> WardrobeSnapshot:
            assert user_id == "trusted-user"
            return WardrobeSnapshot(
                version=7,
                observed_at=datetime.now(timezone.utc),
                items=[WardrobeItem("shirt-1", None, "White shirt", "Shirt", "White", None)],
            )

    workflow, orchestrator = create_workflow(tmp_path)
    orchestrator.wardrobe_provider = FixtureWardrobe()
    try:
        response = workflow.invoke(
            task_id="wardrobe-task",
            message="Plan 2 outfits from my wardrobe for an interview, budget 200",
            session_id="wardrobe-session",
            trusted_user_id="trusted-user",
        )
        state = workflow.get_task_state("wardrobe-task")
    finally:
        workflow.close()

    assert response.intent.value == "wardrobe_plan"
    assert response.wardrobe_plan is not None
    assert response.wardrobe_plan["wardrobe_version"] == 7
    assert state["context_refs"]["wardrobe_version"] == 7
    assert response.tool_trace[0].tool == "search_products_by_text"


def test_transient_retrieval_error_retries_only_failed_node(tmp_path: Path) -> None:
    workflow, orchestrator = create_workflow(tmp_path)
    original_invoke = orchestrator.registry.invoke
    attempts = 0

    def flaky_invoke(name, arguments):
        nonlocal attempts
        if name == "search_products_by_text":
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary retrieval failure")
        return original_invoke(name, arguments)

    orchestrator.registry.invoke = flaky_invoke
    try:
        items = list(
            workflow.stream(
                task_id="retry-node",
                message="推荐一件红色衬衫",
                session_id="retry-session",
                request_id="retry-request",
            )
        )
        state = workflow.get_task_state("retry-node")
    finally:
        workflow.close()

    node_events = [item["data"] for item in items if item["type"] == "node"]
    assert attempts == 2
    assert (
        sum(
            event["node"] == "retrieve_candidates" and event["state"] == "started"
            for event in node_events
        )
        == 2
    )
    assert any(
        event["node"] == "retrieve_candidates" and event["state"] == "failed"
        for event in node_events
    )
    assert len(state["executed_nodes"]) == len(set(state["executed_nodes"]))


def test_process_restart_resumes_last_checkpoint_without_repeating_nodes(
    tmp_path: Path,
) -> None:
    first, first_orchestrator = create_workflow(tmp_path / "first")

    def unavailable_retrieval(_name, _arguments):
        raise RuntimeError("retrieval is offline")

    first_orchestrator.registry.invoke = unavailable_retrieval
    with pytest.raises(RuntimeError, match="retrieval is offline"):
        invoke_recommendation(first, "restart-task")
    failed_state = first.get_task_state("restart-task")
    first.close()

    second, _ = create_workflow(tmp_path / "second")
    try:
        response = invoke_recommendation(
            second,
            "restart-task",
            request_id="recovered-request",
        )
        completed_state = second.get_task_state("restart-task")
    finally:
        second.close()

    assert failed_state["executed_nodes"] == [
        "validate_input",
        "understand_request",
        "load_context",
        "plan_tools",
    ]
    assert response.recovered is True
    assert response.request_id == "recovered-request"
    assert completed_state["executed_nodes"][:4] == failed_state["executed_nodes"]
    assert len(completed_state["executed_nodes"]) == len(
        set(completed_state["executed_nodes"])
    )


def test_image_recovery_accepts_reuploaded_file_when_saved_path_is_gone(
    tmp_path: Path,
) -> None:
    first, first_orchestrator = create_workflow(tmp_path / "image-first")
    fixture_image = (
        tmp_path / "image-first" / "indexes" / "images" / "000" / "0000000001.jpg"
    )
    old_upload = tmp_path / "old-upload.jpg"
    replacement_upload = tmp_path / "replacement-upload.jpg"
    copyfile(fixture_image, old_upload)
    copyfile(fixture_image, replacement_upload)

    def unavailable_retrieval(_name, _arguments):
        raise RuntimeError("image retrieval is offline")

    first_orchestrator.registry.invoke = unavailable_retrieval
    with pytest.raises(RuntimeError, match="image retrieval is offline"):
        first.invoke(
            task_id="image-restart-task",
            message="",
            session_id="image-restart-session",
            image_path=str(old_upload),
            request_id="image-failed-request",
        )
    old_upload.unlink()
    first.close()

    second, _ = create_workflow(tmp_path / "image-second")
    try:
        response = second.invoke(
            task_id="image-restart-task",
            message="",
            session_id="image-restart-session",
            image_path=str(replacement_upload),
            request_id="image-recovered-request",
        )
        state = second.get_task_state("image-restart-task")
    finally:
        second.close()

    assert response.recovered is True
    assert response.products[0]["article_id"] == "0000000001"
    assert state["planned_arguments"]["image_path"] == str(replacement_upload)


def test_duplicate_completed_task_returns_cached_response_once(tmp_path: Path) -> None:
    workflow, orchestrator = create_workflow(tmp_path)
    original_invoke = orchestrator.registry.invoke
    retrieval_calls = 0

    def counted_invoke(name, arguments):
        nonlocal retrieval_calls
        if name == "search_products_by_text":
            retrieval_calls += 1
        return original_invoke(name, arguments)

    orchestrator.registry.invoke = counted_invoke
    try:
        first = invoke_recommendation(workflow, "duplicate-task")
        second = invoke_recommendation(
            workflow,
            "duplicate-task",
            request_id="duplicate-request-2",
        )
        history = orchestrator.memory.recent_history("workflow-session")
        with pytest.raises(AgentException, match="different input"):
            workflow.invoke(
                task_id="duplicate-task",
                message="推荐黑色裙子",
                session_id="workflow-session",
                request_id="different-input",
            )
    finally:
        workflow.close()

    assert first.recovered is False
    assert second.recovered is True
    assert second.request_id == "duplicate-request-2"
    assert retrieval_calls == 1
    assert len(history) == 2


class FailingRecommendationChain:
    def invoke(self, _inputs):
        raise TimeoutError("LLM unavailable")


def test_llm_unavailable_uses_grounded_fallback_and_completes(tmp_path: Path) -> None:
    generator = GroundedRecommendationGenerator(chain=FailingRecommendationChain())
    workflow, _ = create_workflow(tmp_path, reason_generator=generator)
    try:
        response = invoke_recommendation(workflow, "llm-fallback")
    finally:
        workflow.close()

    assert response.answer == "根据你的需求，我从真实商品库中筛出了这些候选。"
    assert response.products[0]["reason"].startswith("Red Shirt 属于 Shirt")


def test_api_streams_real_node_trace_and_feature_flag_falls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    memory_url = os.getenv("AGENT_MEMORY_DATABASE_URL")
    checkpoint_url = os.getenv("AGENT_CHECKPOINT_DATABASE_URL")
    if not memory_url or not checkpoint_url:
        pytest.skip(
            "AGENT_MEMORY_DATABASE_URL / AGENT_CHECKPOINT_DATABASE_URL are required "
            "for the live API workflow integration test."
        )
    text_index, image_index, _ = build_fixture_indexes(tmp_path / "api-indexes")
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(image_index))
    monkeypatch.setenv("AGENT_MEMORY_DATABASE_URL", memory_url)
    monkeypatch.setenv("AGENT_CHECKPOINT_DATABASE_URL", checkpoint_url)
    monkeypatch.setenv("AGENT_CHECKPOINT_AUTO_SETUP", "true")
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "test-agent-context-token")
    monkeypatch.setenv("AGENT_WORKFLOW_ENABLED", "true")
    get_memory.cache_clear()
    get_orchestrator.cache_clear()
    reset_workflow()

    try:
        with TestClient(app) as client:
            owner_headers = {
                "X-Agent-Context-Token": "test-agent-context-token",
                "X-Trusted-User-Id": "workflow-owner",
            }
            streamed = client.post(
                "/api/chat/stream",
                data={
                    "task_id": "api-node-trace",
                    "message": "推荐一件红色衬衫",
                    "session_id": "api-workflow",
                },
                headers=owner_headers,
            )
            assert streamed.status_code == 200
            assert streamed.headers["X-Agent-Task-Id"] == "api-node-trace"
            assert (
                'event: node\ndata: {"node": "validate_input", "state": "started"}'
                in streamed.text
            )
            assert streamed.text.index("event: node") < streamed.text.index(
                "event: meta"
            )
            assert streamed.text.index("event: message") < streamed.text.index(
                "event: meta"
            )

            duplicate = client.post(
                "/api/chat/stream",
                data={
                    "task_id": "api-node-trace",
                    "message": "推荐一件红色衬衫",
                    "session_id": "api-workflow",
                },
                headers=owner_headers,
            )
            assert "event: node" not in duplicate.text
            assert '"recovered": true' in duplicate.text

            monkeypatch.setenv("AGENT_WORKFLOW_ENABLED", "false")
            legacy = client.post(
                "/api/chat/stream",
                data={
                    "task_id": "legacy-flag-off",
                    "message": "推荐一件红色衬衫",
                    "session_id": "legacy-workflow",
                },
                headers=owner_headers,
            )
            assert legacy.status_code == 200
            assert "event: node" not in legacy.text
            assert "event: products" in legacy.text
    finally:
        reset_workflow()
        get_orchestrator.cache_clear()
        get_memory.cache_clear()


@pytest.mark.parametrize("invalid", ["", "contains space", "a" * 101, "../task"])
def test_task_id_validation_rejects_unsafe_values(invalid: str) -> None:
    with pytest.raises(AgentException):
        validate_task_id(invalid)
