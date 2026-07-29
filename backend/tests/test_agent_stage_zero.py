from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.contracts import ErrorCode, Intent
from app.core.agent.errors import AgentException
from app.core.agent.memory import AgentMemoryStore
from app.core.agent.planner import AgentPlanner
from app.core.agent.tool_registry import ToolRegistry
from app.main import app


def test_request_id_is_preserved_and_invalid_value_is_replaced() -> None:
    with TestClient(app) as client:
        preserved = client.get("/health", headers={"X-Request-Id": "web.request-123"})
        assert preserved.headers["X-Request-Id"] == "web.request-123"

        replaced = client.get("/health", headers={"X-Request-Id": "../invalid request"})
        generated = replaced.headers["X-Request-Id"]
        assert generated != "../invalid request"
        assert len(generated) == 32


def test_invalid_session_and_request_validation_use_typed_errors() -> None:
    with TestClient(app) as client:
        invalid_session = client.post(
            "/api/chat",
            data={"message": "推荐衬衫", "session_id": "invalid/session"},
            headers={"X-Request-Id": "invalid-session-test"},
        )
        assert invalid_session.status_code == 400
        assert invalid_session.headers["X-Request-Id"] == "invalid-session-test"
        payload = invalid_session.json()
        assert payload["detail"]
        assert payload["error"] == {
            "request_id": "invalid-session-test",
            "code": "INVALID_SESSION_ID",
            "message": payload["detail"],
            "retryable": False,
            "stage": "validate_input",
            "details": {},
        }

        invalid_language = client.post(
            "/api/chat",
            data={"message": "推荐衬衫", "language": "fr"},
            headers={"X-Request-Id": "validation-test"},
        )
        assert invalid_language.status_code == 422
        error = invalid_language.json()["error"]
        assert error["request_id"] == "validation-test"
        assert error["code"] == "INVALID_INPUT"
        assert error["details"]["errors"]


def test_overlong_session_id_returns_specific_error() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/session",
            json={"session_id": "a" * 101},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SESSION_ID"


def test_stream_error_is_classified_and_contains_request_id(monkeypatch) -> None:
    chat_module = importlib.import_module("app.api.chat")

    class FailingOrchestrator:
        def handle(self, *args, **kwargs):
            raise RuntimeError("retriever failed")

    monkeypatch.setattr(chat_module, "get_orchestrator", lambda: FailingOrchestrator())

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/stream",
            data={"message": "推荐衬衫", "session_id": "stream-error"},
            headers={"X-Request-Id": "stream-error-test"},
        )
    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "stream-error-test"
    blocks = [block for block in response.text.split("\n\n") if block]
    assert "event: status" in blocks[0]
    error_block = next(block for block in blocks if "event: error" in block)
    data_line = next(line for line in error_block.splitlines() if line.startswith("data:"))
    error = json.loads(data_line.removeprefix("data:").strip())
    assert error["request_id"] == "stream-error-test"
    assert error["code"] == "RETRIEVAL_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["stage"] == "agent"


def test_unknown_tool_and_invalid_arguments_are_classified() -> None:
    registry = ToolRegistry()

    with pytest.raises(AgentException) as unknown:
        registry.invoke("missing_tool", {})
    assert unknown.value.code == ErrorCode.TOOL_NOT_FOUND

    def positive_top_k(top_k: int) -> int:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        return top_k

    registry.register("positive_top_k", "Validate top_k.", positive_top_k)
    with pytest.raises(AgentException) as invalid:
        registry.invoke("positive_top_k", {"top_k": 0})
    assert invalid.value.code == ErrorCode.INVALID_TOOL_ARGUMENT
    assert invalid.value.details["tool"] == "positive_top_k"


def test_session_ttl_removes_expired_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "60")
    database = tmp_path / "sessions.db"
    memory = AgentMemoryStore(database)
    memory.add_user_message("expired-session", "旧消息")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_sessions SET updated_at = '2000-01-01 00:00:00' "
            "WHERE session_id = 'expired-session'"
        )

    restored = AgentMemoryStore(database)
    assert restored.recent_history("expired-session") == []


def test_intent_is_a_string_enum() -> None:
    assert Intent.TEXT_RECOMMENDATION == "text_recommendation"
    assert Intent.CART_HANDOFF.value == "cart_handoff"


@pytest.mark.parametrize(
    ("message", "selected_tool", "expected"),
    [
        ("找相似的通勤款", "search_products_by_text", Intent.HYBRID_SEARCH),
        ("", "search_products_by_text", Intent.IMAGE_SEARCH),
    ],
)
def test_planner_cannot_drop_uploaded_image(
    message: str,
    selected_tool: str,
    expected: Intent,
) -> None:
    class FakeBoundModel:
        def invoke(self, _messages):
            return SimpleNamespace(tool_calls=[{"name": selected_tool}])

    planner = AgentPlanner.__new__(AgentPlanner)
    planner.bound = FakeBoundModel()

    chosen = planner.choose(message, has_image=True, fallback=lambda: expected)

    assert chosen == expected


@pytest.mark.parametrize("expected", [Intent.CART_HANDOFF, Intent.COMPARE])
def test_planner_preserves_deterministic_business_routes(expected: Intent) -> None:
    class IncorrectBoundModel:
        def invoke(self, _messages):
            return SimpleNamespace(
                tool_calls=[{"name": "search_products_by_text"}]
            )

    planner = AgentPlanner.__new__(AgentPlanner)
    planner.bound = IncorrectBoundModel()

    chosen = planner.choose("业务关键词", has_image=False, fallback=lambda: expected)

    assert chosen == expected
