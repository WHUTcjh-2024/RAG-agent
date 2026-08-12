from __future__ import annotations

# ruff: noqa: E402

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.decision import DecisionFacts
from app.core.agent.wardrobe import WardrobeItem, WardrobeSnapshot
from app.mcp.server import (
    MCP_API_VERSION,
    ShoppingMcpService,
    TrustedMcpContextMiddleware,
    _trusted_user_context,
    create_mcp_server,
)


class FakeRegistry:
    def invoke(self, name: str, arguments: dict) -> dict:
        if name == "search_products_by_text":
            return {
                "results": [
                    {
                        "article_id": "0000000001",
                        "prod_name": "Red Shirt",
                        "price": 99,
                    }
                ],
                "total_candidates": 1,
            }
        if name == "get_product_detail":
            return {
                "article_id": arguments["product_id"],
                "prod_name": "Red Shirt",
                "price": 99,
            }
        raise AssertionError(f"Unexpected tool: {name}")


class FakeWardrobeProvider:
    def get(self, *, user_id: str) -> WardrobeSnapshot:
        assert user_id == "user-1"
        return WardrobeSnapshot(
            version=4,
            observed_at=datetime.now(timezone.utc),
            items=[
                WardrobeItem(
                    id="wardrobe-1",
                    source_product_id=None,
                    name="Blue Jeans",
                    category="BOTTOM",
                    color="Blue",
                    image_url=None,
                )
            ],
        )


class FakeDecisionFactsProvider:
    def get(self, *, user_id: str, product_id: str) -> DecisionFacts:
        assert user_id == "user-1"
        return DecisionFacts(
            user_id=user_id,
            product_id=product_id,
            sku_id="sku-1",
            profile={"chest_cm": 88},
            sku_measurements={"chest_cm": 96, "size": "M"},
            price={"amount": 99},
            inventory={"in_stock": True},
            return_policy={"summary": "7 days"},
            version="fact-v1",
            observed_at=datetime.now(timezone.utc),
            provenance={"price.amount": {"verified": True}},
        )


class FakeTryOnService:
    configured = False


def make_server():
    return create_mcp_server(
        ShoppingMcpService(
            registry_provider=FakeRegistry,
            product_loader=lambda product_id: {"article_id": product_id},
            try_on_service_provider=FakeTryOnService,
            wardrobe_provider=FakeWardrobeProvider(),
            decision_facts_provider=FakeDecisionFactsProvider(),
        )
    )


def test_mcp_tools_publish_versioned_schemas_and_safe_annotations() -> None:
    server = make_server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    assert set(tools) == {
        "catalog_search",
        "catalog_get_product",
        "decision_facts_get",
        "wardrobe_get_snapshot",
        "wardrobe_plan_outfits",
        "try_on_create_preview",
        "cart_prepare_add",
    }
    assert tools["catalog_search"].annotations.readOnlyHint is True
    assert tools["cart_prepare_add"].annotations.readOnlyHint is True
    assert "context_token" not in tools["cart_prepare_add"].inputSchema["properties"]
    assert "trusted_user_id" not in tools["wardrobe_get_snapshot"].inputSchema["properties"]
    assert tools["cart_prepare_add"].inputSchema["properties"]["user_confirmed"]["const"] is True
    assert tools["try_on_create_preview"].inputSchema["properties"]["user_confirmed"]["const"] is True


def test_catalog_tool_uses_registry_and_returns_policy_metadata() -> None:
    server = make_server()

    result = asyncio.run(server.call_tool("catalog_search", {"query": "red shirt"}))

    content, structured = result
    assert content[0].text
    assert structured["api_version"] == "v1"
    assert structured["data"]["items"][0]["article_id"] == "0000000001"


def test_java_wardrobe_tool_requires_trusted_context() -> None:
    server = make_server()

    with pytest.raises(Exception, match="Trusted user context is required"):
        asyncio.run(server.call_tool("wardrobe_get_snapshot", {}))

    token = _trusted_user_context.set("user-1")
    try:
        result = asyncio.run(server.call_tool("wardrobe_get_snapshot", {}))
    finally:
        _trusted_user_context.reset(token)
    _content, structured = result
    assert structured["policy"]["authority"] == "java-business"
    assert structured["data"]["version"] == 4


def test_decision_facts_tool_reads_java_authority_with_trusted_user_context() -> None:
    server = make_server()
    token = _trusted_user_context.set("user-1")
    try:
        _content, structured = asyncio.run(
            server.call_tool("decision_facts_get", {"product_id": "0000000001"})
        )
    finally:
        _trusted_user_context.reset(token)

    assert structured["policy"]["authority"] == "java-business"
    assert structured["data"]["price"] == {"amount": 99}
    assert structured["data"]["provenance"]["price.amount"]["verified"] is True


def test_cart_prepare_never_mutates_cart_and_requires_explicit_confirmation(monkeypatch) -> None:
    server = make_server()
    monkeypatch.setenv("AGENT_ACTION_SECRET", "mcp-action-secret")

    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "cart_prepare_add",
                {
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "product_id": "0000000001",
                    "user_confirmed": False,
                },
            )
        )

    token = _trusted_user_context.set("user-1")
    try:
        result = asyncio.run(
            server.call_tool(
                "cart_prepare_add",
                {
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "product_id": "0000000001",
                    "user_confirmed": True,
                },
            )
        )
    finally:
        _trusted_user_context.reset(token)
    _content, structured = result
    assert structured["data"]["writes_performed"] is False
    assert structured["data"]["confirmation"]["confirmation_token"]
    assert structured["api_version"] == MCP_API_VERSION


def test_http_context_middleware_keeps_credentials_out_of_tool_arguments(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "mcp-context-token-123")
    app = FastAPI()
    app.add_middleware(TrustedMcpContextMiddleware)

    @app.get("/whoami")
    def whoami() -> dict[str, str | None]:
        return {"user_id": _trusted_user_context.get()}

    with TestClient(app) as client:
        assert client.get("/whoami").json() == {"user_id": None}
        rejected = client.get(
            "/whoami", headers={"X-Trusted-User-Id": "user-1"}
        )
        assert rejected.status_code == 401
        accepted = client.get(
            "/whoami",
            headers={
                "X-Trusted-User-Id": "user-1",
                "X-Agent-Context-Token": "mcp-context-token-123",
            },
        )
        assert accepted.json() == {"user_id": "user-1"}


def test_mcp_streamable_http_discovers_tools_and_rejects_untrusted_user_scope(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "mcp-context-token-123")
    app = FastAPI()
    mcp_app = make_server().streamable_http_app()
    mcp_app.add_middleware(TrustedMcpContextMiddleware)
    app.mount("/mcp", mcp_app)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
            headers={"Host": "localhost:80"},
        ) as client:
            async with mcp_app.router.lifespan_context(mcp_app):
                async with streamable_http_client("http://localhost/mcp/", http_client=client) as streams:
                    read_stream, write_stream, _session_id = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        assert "cart_prepare_add" in {tool.name for tool in tools.tools}
                        denied = await session.call_tool("wardrobe_get_snapshot")
                        assert denied.isError is True

    asyncio.run(exercise())
