from __future__ import annotations

# ruff: noqa: E402

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.chat import get_memory, get_orchestrator, reset_workflow
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.llm import (
    GroundedRecommendation,
    GroundedRecommendationGenerator,
    ProductReason,
)
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever
from app.main import app
from tests.postgres_helpers import require_postgres
from tests.test_hybrid_retrieval import build_fixture_indexes


def create_orchestrator(root: Path) -> ShoppingAgentOrchestrator:
    text_index, image_index, _ = build_fixture_indexes(root)
    return ShoppingAgentOrchestrator(
        text_retriever=TextRetriever(text_index),
        image_retriever=ImageRetriever(image_index, device="cpu"),
        hybrid_retriever=HybridRetriever(text_index, image_index, image_device="cpu"),
    )


def test_registry_contains_real_langchain_tools(tmp_path: Path) -> None:
    orchestrator = create_orchestrator(tmp_path)
    assert len(orchestrator.registry.tools) == 6
    assert all(isinstance(tool, BaseTool) for tool in orchestrator.registry.tools)
    assert "hybrid_search" in orchestrator.registry.names
    assert "update_user_preference" in orchestrator.registry.names


def test_agent_recommend_compare_and_handoff_cart(tmp_path: Path) -> None:
    orchestrator = create_orchestrator(tmp_path)
    session_id = "agent-flow"

    assert orchestrator.slot_extractor.extract("推荐一件红色衬衫") == {
        "color": "Red",
        "category": "Shirt",
    }
    recommendation = orchestrator.handle("推荐两件衬衫", session_id)
    assert recommendation.intent == "text_recommendation"
    assert recommendation.products
    assert len(recommendation.products) == 2
    assert recommendation.slots["category"] == "Shirt"
    assert any(trace.tool == "search_products_by_text" for trace in recommendation.tool_trace)

    comparison = orchestrator.handle("对比第1件和第2件", session_id)
    assert comparison.intent == "compare"
    assert len(comparison.comparison) == 2

    cart = orchestrator.handle("把第1件加入购物车", session_id)
    assert cart.intent == "cart_handoff"
    assert "Java" in cart.answer
    assert not any("cart" in trace.tool for trace in cart.tool_trace)


class FakeHallucinatingChain:
    def invoke(self, inputs):
        return GroundedRecommendation(
            recommendations=[
                ProductReason(article_id="9999999999"),
                ProductReason(article_id="0000000001"),
            ],
        )


class FakeFailingChain:
    def invoke(self, inputs):
        raise TimeoutError("model timed out")


def test_llm_product_id_whitelist_drops_hallucinations() -> None:
    generator = GroundedRecommendationGenerator(chain=FakeHallucinatingChain())
    intro, reasons = generator.generate(
        user_query="推荐红色衬衫",
        products=[
            {
                "article_id": "0000000001",
                "prod_name": "Red Shirt",
                "product_type_name": "Shirt",
                "colour_group_name": "Red",
            }
        ],
        slots={"color": "Red", "category": "Shirt"},
        history=[],
    )
    assert intro == "根据你的需求，我从真实商品库中筛出了这些候选。"
    assert reasons == {
        "0000000001": "Red Shirt 属于 Shirt，颜色为 Red，来自与当前需求匹配的商品目录。"
    }
    assert "9999999999" not in reasons


def test_model_selection_schema_rejects_freeform_recommendation_facts() -> None:
    with pytest.raises(ValidationError):
        GroundedRecommendation.model_validate(
            {
                "recommendations": [
                    {"article_id": "0000000001", "reason": "现货 99 元羊毛"}
                ]
            }
        )


def test_llm_failure_is_logged_and_falls_back(caplog) -> None:
    generator = GroundedRecommendationGenerator(chain=FakeFailingChain())
    with caplog.at_level("WARNING"):
        intro, reasons = generator.generate(
            user_query="推荐红色衬衫",
            products=[
                {
                    "article_id": "0000000001",
                    "prod_name": "Red Shirt",
                    "product_type_name": "Shirt",
                    "colour_group_name": "Red",
                }
            ],
            slots={"color": "Red", "category": "Shirt"},
            history=[],
        )
    assert intro == "根据你的需求，我从真实商品库中筛出了这些候选。"
    assert reasons == {
        "0000000001": "Red Shirt 属于 Shirt，颜色为 Red，与当前检索条件匹配。"
    }
    assert "code=MODEL_UNAVAILABLE" in caplog.text
    assert "stage=generate_answer" in caplog.text


def test_chat_api_and_sse_tool_trace(tmp_path: Path, monkeypatch) -> None:
    memory_url = os.getenv("AGENT_MEMORY_DATABASE_URL")
    checkpoint_url = os.getenv("AGENT_CHECKPOINT_DATABASE_URL")
    if not memory_url or not checkpoint_url:
        pytest.skip(
            "AGENT_MEMORY_DATABASE_URL / AGENT_CHECKPOINT_DATABASE_URL are required "
            "for the live agent API integration test."
        )
    text_index, image_index, _ = build_fixture_indexes(tmp_path)
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(image_index))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("AGENT_MEMORY_DATABASE_URL", memory_url)
    monkeypatch.setenv("AGENT_CHECKPOINT_DATABASE_URL", checkpoint_url)
    monkeypatch.setenv("AGENT_MEMORY_AUTO_SETUP", "true")
    monkeypatch.setenv("AGENT_CHECKPOINT_AUTO_SETUP", "true")
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "test-agent-context-token")
    get_memory.cache_clear()
    get_orchestrator.cache_clear()
    reset_workflow()
    owner_headers = {
        "X-Agent-Context-Token": "test-agent-context-token",
        "X-Trusted-User-Id": "owner-a",
    }
    other_owner_headers = {
        "X-Agent-Context-Token": "test-agent-context-token",
        "X-Trusted-User-Id": "owner-b",
    }

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                data={"message": "推荐一件红色衬衫", "session_id": "api-agent"},
                headers=owner_headers,
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["request_id"]
            assert payload["products"][0]["article_id"] == "0000000001"
            assert payload["tool_trace"][-1]["tool"] == "search_products_by_text"

            english = client.post(
                "/api/chat",
                data={"message": "Recommend a red shirt", "session_id": "api-en", "language": "en"},
                headers=owner_headers,
            )
            assert english.status_code == 200
            assert english.json()["answer"] == "I selected these candidates from the real product catalog."

            restored = client.post(
                "/api/session", json={"session_id": "api-agent"}, headers=owner_headers
            )
            assert restored.status_code == 200
            assert restored.json()["slots"] == {"color": "Red", "category": "Shirt"}
            assert restored.json()["history"]

            assert client.post("/api/session", json={"session_id": "api-agent"}).status_code == 401
            assert client.post(
                "/api/session", json={"session_id": "api-agent"}, headers=other_owner_headers
            ).status_code == 404
            assert client.post(
                "/api/chat", data={"message": "Recommend a red shirt", "session_id": "api-agent"},
                headers=other_owner_headers,
            ).status_code == 404

            get_memory().add_user_message("legacy-session", "legacy data")
            assert client.post(
                "/api/chat", data={"message": "Recommend a red shirt", "session_id": "legacy-session"},
                headers=owner_headers,
            ).status_code == 404

            anonymous = client.post(
                "/api/chat",
                data={
                    "message": "Recommend a red shirt",
                    "session_id": "api-agent",
                    "task_id": "attacker-controlled-task",
                },
            )
            assert anonymous.status_code == 200
            assert anonymous.json()["session_id"] != "api-agent"
            assert anonymous.json()["task_id"] != "attacker-controlled-task"
            assert client.post(
                "/api/session", json={"session_id": "api-agent"}, headers=owner_headers
            ).status_code == 200

            stream = client.post(
                "/api/chat/stream",
                data={"message": "继续推荐红色衬衫", "session_id": "api-agent"},
                headers=owner_headers,
            )
            assert stream.status_code == 200
            assert "event: meta" in stream.text
            assert "event: tool" in stream.text
            assert "event: done" in stream.text
            assert stream.headers["X-Request-Id"]

            assert client.delete("/api/session/api-agent").status_code == 401
            assert client.delete("/api/session/api-agent", headers=other_owner_headers).status_code == 404
            assert client.delete("/api/session/api-agent", headers=owner_headers).status_code == 200
            assert client.post(
                "/api/session", json={"session_id": "api-agent"}, headers=owner_headers
            ).status_code == 404
    finally:
        reset_workflow()
        get_orchestrator.cache_clear()
        get_memory.cache_clear()


def test_text_agent_works_without_optional_image_index(
    tmp_path: Path, monkeypatch
) -> None:
    text_index, _, query_image = build_fixture_indexes(tmp_path / "fixtures")
    missing_image_index = tmp_path / "missing-image-index"
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(missing_image_index))
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_orchestrator.cache_clear()

    try:
        orchestrator = get_orchestrator()
        assert "search_products_by_text" in orchestrator.registry.names
        assert "search_products_by_image" not in orchestrator.registry.names
        assert "hybrid_search" not in orchestrator.registry.names

        with TestClient(app) as client:
            response = client.post(
                "/api/chat/stream",
                data={"message": "Recommend a red shirt", "session_id": "text-only"},
            )

        assert response.status_code == 200
        assert "event: products" in response.text
        assert "event: message" in response.text
        assert "event: done" in response.text
        assert "event: error" not in response.text

        with TestClient(app) as client, query_image.open("rb") as image:
            unavailable = client.post(
                "/api/chat/stream",
                data={"message": "Find similar products", "session_id": "image-only"},
                files={"file": ("query.jpg", image, "image/jpeg")},
            )

        assert unavailable.status_code == 200
        assert '"code": "INDEX_NOT_READY"' in unavailable.text
        assert "event: done" not in unavailable.text
    finally:
        get_orchestrator.cache_clear()
