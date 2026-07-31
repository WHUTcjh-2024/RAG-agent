from __future__ import annotations

# ruff: noqa: E402

import sqlite3
import sys
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.chat import get_orchestrator, reset_workflow
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
from app.main import app
from tests.test_hybrid_retrieval import build_fixture_indexes


def create_workflow(
    root: Path,
    *,
    session_db: Path | None = None,
    checkpoint_db: Path | None = None,
    reason_generator: GroundedRecommendationGenerator | None = None,
) -> tuple[RecoverableShoppingAgentWorkflow, ShoppingAgentOrchestrator]:
    text_index, image_index, _ = build_fixture_indexes(root / "indexes")
    orchestrator = ShoppingAgentOrchestrator(
        text_retriever=TextRetriever(text_index),
        image_retriever=ImageRetriever(image_index, device="cpu"),
        hybrid_retriever=HybridRetriever(
            text_index,
            image_index,
            image_device="cpu",
        ),
        memory=AgentMemoryStore(session_db or root / "sessions.db"),
        reason_generator=reason_generator,
    )
    workflow = RecoverableShoppingAgentWorkflow(
        orchestrator,
        checkpoint_db or root / "checkpoints.db",
    )
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

    with sqlite3.connect(tmp_path / "checkpoints.db") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"checkpoints", "writes"} <= tables


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
    assert "Java" in response.answer
    assert response.tool_trace == []
    assert workflow.route_after_answer({"pending_action": {"type": "handoff"}}) == (
        "wait_for_confirmation"
    )
    assert workflow.route_after_answer({"pending_action": None}) == "complete"


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
    session_db = tmp_path / "sessions.db"
    checkpoint_db = tmp_path / "checkpoints.db"
    first, first_orchestrator = create_workflow(
        tmp_path / "first",
        session_db=session_db,
        checkpoint_db=checkpoint_db,
    )

    def unavailable_retrieval(_name, _arguments):
        raise RuntimeError("retrieval is offline")

    first_orchestrator.registry.invoke = unavailable_retrieval
    with pytest.raises(RuntimeError, match="retrieval is offline"):
        invoke_recommendation(first, "restart-task")
    failed_state = first.get_task_state("restart-task")
    first.close()

    second, _ = create_workflow(
        tmp_path / "second",
        session_db=session_db,
        checkpoint_db=checkpoint_db,
    )
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
    session_db = tmp_path / "image-sessions.db"
    checkpoint_db = tmp_path / "image-checkpoints.db"
    first, first_orchestrator = create_workflow(
        tmp_path / "image-first",
        session_db=session_db,
        checkpoint_db=checkpoint_db,
    )
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

    second, _ = create_workflow(
        tmp_path / "image-second",
        session_db=session_db,
        checkpoint_db=checkpoint_db,
    )
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
    text_index, image_index, _ = build_fixture_indexes(tmp_path / "api-indexes")
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(image_index))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "api-sessions.db"))
    monkeypatch.setenv(
        "AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "api-checkpoints.db"),
    )
    monkeypatch.setenv("AGENT_WORKFLOW_ENABLED", "true")
    get_orchestrator.cache_clear()
    reset_workflow()

    try:
        with TestClient(app) as client:
            streamed = client.post(
                "/api/chat/stream",
                data={
                    "task_id": "api-node-trace",
                    "message": "推荐一件红色衬衫",
                    "session_id": "api-workflow",
                },
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

            duplicate = client.post(
                "/api/chat/stream",
                data={
                    "task_id": "api-node-trace",
                    "message": "推荐一件红色衬衫",
                    "session_id": "api-workflow",
                },
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
            )
            assert legacy.status_code == 200
            assert "event: node" not in legacy.text
            assert "event: products" in legacy.text
    finally:
        reset_workflow()
        get_orchestrator.cache_clear()


@pytest.mark.parametrize("invalid", ["", "contains space", "a" * 101, "../task"])
def test_task_id_validation_rejects_unsafe_values(invalid: str) -> None:
    with pytest.raises(AgentException):
        validate_task_id(invalid)
