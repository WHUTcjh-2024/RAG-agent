from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Annotated, Any, Callable, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.agent.contracts import ErrorCode
from app.core.agent.decision import DecisionFactsProvider, JavaDecisionFactsProvider
from app.core.agent.errors import AgentException, classify_exception, invalid_input
from app.core.agent.memory import validate_session_id
from app.core.agent.telemetry import telemetry
from app.core.agent.wardrobe import JavaWardrobeProvider, WardrobePlanner
from app.core.virtual_try_on import SyntheticBodyProfile, TryOnError


logger = logging.getLogger(__name__)
MCP_PROTOCOL_VERSION = "2026-08-12"
MCP_API_VERSION = "v1"
_CONTEXT_TOKEN_HEADER = "x-agent-context-token"
_TRUSTED_USER_HEADER = "x-trusted-user-id"
_MAX_TOOL_RESULTS = 20

NonEmptyText = Annotated[str, Field(min_length=1, max_length=500)]
ProductId = Annotated[str, Field(min_length=1, max_length=128)]
SessionId = Annotated[str, Field(min_length=1, max_length=100)]
_trusted_user_context: ContextVar[str | None] = ContextVar(
    "trusted_mcp_user", default=None
)


class ToolAccess(str, Enum):
    READ = "READ"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"


@dataclass(frozen=True)
class ToolPolicy:
    access: ToolAccess
    authority: str
    permission: str
    purpose: str


TOOL_POLICIES: dict[str, ToolPolicy] = {
    "catalog_search": ToolPolicy(
        ToolAccess.READ, "catalog", "catalog:read", "Search real catalog candidates only."
    ),
    "catalog_get_product": ToolPolicy(
        ToolAccess.READ, "catalog", "catalog:read", "Read one real catalog product."
    ),
    "decision_facts_get": ToolPolicy(
        ToolAccess.READ,
        "java-business",
        "decision_facts:read",
        "Read provenance-bearing product and body facts from Java business service.",
    ),
    "wardrobe_get_snapshot": ToolPolicy(
        ToolAccess.READ, "java-business", "wardrobe:read", "Read the versioned wardrobe owned by Java."
    ),
    "wardrobe_plan_outfits": ToolPolicy(
        ToolAccess.READ, "java-business", "wardrobe:read", "Generate a deterministic read-only outfit plan."
    ),
    "try_on_create_preview": ToolPolicy(
        ToolAccess.CONFIRMATION_REQUIRED,
        "try-on", "try_on:create", "Create an AI-generated synthetic-model preview after explicit confirmation."
    ),
    "cart_prepare_add": ToolPolicy(
        ToolAccess.CONFIRMATION_REQUIRED,
        "java-business", "cart:prepare", "Prepare, but never execute, a Java-authoritative cart addition."
    ),
}


def _limit(value: int, *, default: int, maximum: int = _MAX_TOOL_RESULTS) -> int:
    return max(1, min(value or default, maximum))


def _trusted_user_id() -> str:
    user_id = _trusted_user_context.get()
    if not user_id:
        raise invalid_input(
            "Trusted user context is required.", status_code=401, stage="authorize_mcp"
        )
    return user_id


class TrustedMcpContextMiddleware(BaseHTTPMiddleware):
    """Admits user-scoped MCP calls only from the internal gateway context.

    The shared service token is intentionally validated in HTTP headers rather than
    tool arguments, so it is never included in model-visible MCP input or traces.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        supplied_token = request.headers.get(_CONTEXT_TOKEN_HEADER, "").strip()
        user_id = request.headers.get(_TRUSTED_USER_HEADER, "").strip()
        expected_token = os.getenv("AGENT_CONTEXT_TOKEN", "").strip()
        if supplied_token or user_id:
            if not expected_token or supplied_token != expected_token or not user_id:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Trusted MCP context is invalid."},
                )
        context_token: Token[str | None] = _trusted_user_context.set(user_id or None)
        try:
            return await call_next(request)
        finally:
            _trusted_user_context.reset(context_token)


def _summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and "results" in value:
        return {"result_count": len(value["results"])}
    if isinstance(value, dict) and "items" in value:
        return {"item_count": len(value["items"])}
    return {"completed": True}


def _result(
    *, policy: ToolPolicy, name: str, value: Any
) -> dict[str, Any]:
    return {
        "tool": name,
        "api_version": MCP_API_VERSION,
        "policy": {
            "access": policy.access.value,
            "authority": policy.authority,
            "permission": policy.permission,
        },
        "summary": _summary(value),
        "data": value,
    }


class ShoppingMcpService:
    """Calls existing domain services without creating a second business write path."""

    def __init__(
        self,
        *,
        registry_provider: Callable[[], Any],
        product_loader: Callable[[str], dict[str, Any]],
        try_on_service_provider: Callable[[], Any],
        wardrobe_provider: JavaWardrobeProvider | None = None,
        decision_facts_provider: DecisionFactsProvider | None = None,
    ) -> None:
        self._registry_provider = registry_provider
        self._product_loader = product_loader
        self._try_on_service_provider = try_on_service_provider
        self._wardrobe_provider = wardrobe_provider or JavaWardrobeProvider()
        self._decision_facts_provider = decision_facts_provider or JavaDecisionFactsProvider()

    def catalog_search(
        self, *, query: str, filters: dict[str, str], limit: int
    ) -> dict[str, Any]:
        result = self._registry_provider().invoke(
            "search_products_by_text",
            {"query": query, "filters": filters, "top_k": limit},
        )
        return {
            "items": result["results"],
            "total_candidates": result["total_candidates"],
            "source": "catalog",
        }

    def catalog_get_product(self, *, product_id: str) -> dict[str, Any]:
        product = self._registry_provider().invoke(
            "get_product_detail", {"product_id": product_id}
        )
        return {"item": product, "source": "catalog"}

    def decision_facts_get(self, *, user_id: str, product_id: str) -> dict[str, Any]:
        facts = self._decision_facts_provider.get(
            user_id=user_id, product_id=product_id
        )
        if facts is None:
            raise AgentException(
                ErrorCode.BUSINESS_FACT_UNAVAILABLE,
                "Java business facts are not configured.",
                status_code=503,
                retryable=True,
                stage="load_business_facts",
            )
        return {
            "user_id": facts.user_id,
            "product_id": facts.product_id,
            "sku_id": facts.sku_id,
            "profile": facts.profile,
            "sku_measurements": facts.sku_measurements,
            "price": facts.price,
            "inventory": facts.inventory,
            "return_policy": facts.return_policy,
            "version": facts.version,
            "observed_at": facts.observed_at.isoformat(),
            "provenance": facts.provenance,
            "authority": "java-business",
        }

    def wardrobe_get_snapshot(self, *, user_id: str) -> dict[str, Any]:
        snapshot = self._wardrobe_provider.get(user_id=user_id)
        return {
            "version": snapshot.version,
            "observed_at": snapshot.observed_at.isoformat(),
            "items": [
                {
                    "id": item.id,
                    "source_product_id": item.source_product_id,
                    "name": item.name,
                    "category": item.category,
                    "color": item.color,
                    "image_url": item.image_url,
                }
                for item in snapshot.items
            ],
            "authority": "java-business",
        }

    def wardrobe_plan_outfits(
        self, *, user_id: str, slots: dict[str, Any], limit: int
    ) -> dict[str, Any]:
        snapshot = self._wardrobe_provider.get(user_id=user_id)
        candidates = self.catalog_search(
            query=str(slots.get("query") or slots.get("scenario") or "outfit"),
            filters={key: str(value) for key, value in slots.get("filters", {}).items()},
            limit=limit,
        )["items"]
        return WardrobePlanner().create_plan(
            snapshot=snapshot,
            slots=slots,
            candidates=candidates,
        )

    async def try_on_create_preview(
        self,
        *,
        user_id: str,
        product_id: str,
        body_profile: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        from app.api.try_on import _job_payload

        service = self._try_on_service_provider()
        if not service.configured:
            raise AgentException(
                code=ErrorCode.BUSINESS_FACT_UNAVAILABLE,
                message="Virtual try-on is not configured.",
                status_code=503,
                retryable=True,
                stage="create_try_on_preview",
            )
        product = self._product_loader(product_id)
        try:
            profile = SyntheticBodyProfile.from_dict(body_profile)
            job, created = service.submit(
                user_id=user_id,
                product=product,
                body_profile=profile,
                idempotency_key=idempotency_key,
            )
            if created:
                await service.dispatch(job.id)
        except TryOnError as error:
            raise invalid_input(str(error), stage="create_try_on_preview") from error
        return {"created": created, "preview": _job_payload(service, job)}


def _run(
    *,
    name: str,
    user_id: str | None,
    operation: Callable[[], Any],
) -> dict[str, Any]:
    policy = TOOL_POLICIES[name]
    with telemetry.span(
        "mcp.tool",
        **{
            "mcp.tool": name,
            "mcp.access": policy.access.value,
            "mcp.authority": policy.authority,
            "mcp.user_present": bool(user_id),
        },
    ):
        try:
            result = operation()
        except AgentException:
            raise
        except Exception as error:
            logger.warning("mcp_tool_failed tool=%s type=%s", name, type(error).__name__)
            raise classify_exception(error, stage=f"mcp.{name}") from error
    return _result(policy=policy, name=name, value=result)


def create_mcp_server(service: ShoppingMcpService) -> FastMCP:
    server = FastMCP(
        "Atelier Shopping MCP",
        instructions=(
            "Provides versioned, grounded shopping tools. Catalog and wardrobe reads are "
            "authoritative only at their owning service. The server has no cart, order, or "
            "payment write tool. Confirmation-required tools must be called only after the user agrees."
        ),
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
    )

    @server.resource(
        "atelier://mcp/v1/capabilities",
        name="Atelier MCP capabilities",
        description="Machine-readable tool policy, version, and authority boundary.",
        mime_type="application/json",
    )
    def capabilities() -> str:
        return json.dumps(
            {
                "api_version": MCP_API_VERSION,
                "protocol_version": MCP_PROTOCOL_VERSION,
                "tools": {
                    name: {
                        "access": policy.access.value,
                        "authority": policy.authority,
                        "permission": policy.permission,
                        "purpose": policy.purpose,
                    }
                    for name, policy in TOOL_POLICIES.items()
                },
                "guarantees": [
                    "Catalog facts are read from the catalog boundary.",
                    "Wardrobe facts are read from Java business service.",
                    "MCP never writes carts, orders, or payments.",
                    "Try-on previews are synthetic and not fit guarantees.",
                ],
            },
            ensure_ascii=False,
        )

    @server.prompt(name="purchase_decision", description="Grounded purchase-decision workflow.")
    def purchase_decision(product_id: ProductId) -> str:
        return (
            f"Use catalog_get_product for {product_id}. If a user asks for fit, retrieve "
            "Java-owned decision facts through the application workflow. Never infer price, "
            "stock, or size. Cart changes require explicit user confirmation."
        )

    @server.tool(
        name="catalog_search",
        description="Search real catalog products with optional structured filters.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def catalog_search(
        query: NonEmptyText,
        filters: dict[str, str] = {},
        limit: Annotated[int, Field(ge=1, le=_MAX_TOOL_RESULTS)] = 5,
    ) -> dict[str, Any]:
        return _run(
            name="catalog_search",
            user_id=None,
            operation=lambda: service.catalog_search(
                query=query.strip(), filters=filters, limit=_limit(limit, default=5)
            ),
        )

    @server.tool(
        name="catalog_get_product",
        description="Read one real catalog product by product ID.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def catalog_get_product(product_id: ProductId) -> dict[str, Any]:
        return _run(
            name="catalog_get_product",
            user_id=None,
            operation=lambda: service.catalog_get_product(product_id=product_id.strip()),
        )

    @server.tool(
        name="decision_facts_get",
        description="Read Java-authoritative body, SKU, price, inventory, return-policy facts and provenance.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def decision_facts_get(product_id: ProductId) -> dict[str, Any]:
        trusted_user_id = _trusted_user_id()
        return _run(
            name="decision_facts_get",
            user_id=trusted_user_id,
            operation=lambda: service.decision_facts_get(
                user_id=trusted_user_id, product_id=product_id.strip()
            ),
        )

    @server.tool(
        name="wardrobe_get_snapshot",
        description="Read the current versioned wardrobe from Java business service.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def wardrobe_get_snapshot() -> dict[str, Any]:
        trusted_user_id = _trusted_user_id()
        return _run(
            name="wardrobe_get_snapshot",
            user_id=trusted_user_id,
            operation=lambda: service.wardrobe_get_snapshot(user_id=trusted_user_id),
        )

    @server.tool(
        name="wardrobe_plan_outfits",
        description="Build a read-only outfit plan from the Java wardrobe and real catalog candidates.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def wardrobe_plan_outfits(
        slots: dict[str, Any],
        candidate_limit: Annotated[int, Field(ge=1, le=_MAX_TOOL_RESULTS)] = 8,
    ) -> dict[str, Any]:
        trusted_user_id = _trusted_user_id()
        return _run(
            name="wardrobe_plan_outfits",
            user_id=trusted_user_id,
            operation=lambda: service.wardrobe_plan_outfits(
                user_id=trusted_user_id,
                slots=slots,
                limit=_limit(candidate_limit, default=8),
            ),
        )

    @server.tool(
        name="try_on_create_preview",
        description="Create a synthetic-model try-on preview after the user has explicitly approved it.",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True
        ),
    )
    async def try_on_create_preview(
        product_id: ProductId,
        body_profile: dict[str, Any],
        idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
        user_confirmed: Literal[True],
    ) -> dict[str, Any]:
        trusted_user_id = _trusted_user_id()
        return await _run_async(
            name="try_on_create_preview",
            user_id=trusted_user_id,
            operation=lambda: service.try_on_create_preview(
                user_id=trusted_user_id,
                product_id=product_id.strip(),
                body_profile=body_profile,
                idempotency_key=idempotency_key,
            ),
        )

    @server.tool(
        name="cart_prepare_add",
        description="Prepare a cart addition for the Java business service; it never writes a cart.",
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
    )
    def cart_prepare_add(
        session_id: SessionId,
        task_id: Annotated[str, Field(min_length=1, max_length=100)],
        product_id: ProductId,
        user_confirmed: Literal[True],
        language: Literal["zh", "en"] = "zh",
    ) -> dict[str, Any]:
        from app.core.agent.actions import create_cart_confirmation

        trusted_user_id = _trusted_user_id()
        validate_session_id(session_id)

        def prepare() -> dict[str, Any]:
            product = service.catalog_get_product(product_id=product_id.strip())["item"]
            action = create_cart_confirmation(
                task_id=task_id,
                user_id=trusted_user_id,
                product=product,
                language=language,
            )
            return {
                "confirmation": action,
                "next_step": "Send confirmation_token to Java POST /api/cart/agent-actions/confirm.",
                "writes_performed": False,
            }

        return _run(name="cart_prepare_add", user_id=trusted_user_id, operation=prepare)

    return server


async def _run_async(
    *, name: str, user_id: str | None, operation: Callable[[], Any]
) -> dict[str, Any]:
    policy = TOOL_POLICIES[name]
    with telemetry.span(
        "mcp.tool",
        **{
            "mcp.tool": name,
            "mcp.access": policy.access.value,
            "mcp.authority": policy.authority,
            "mcp.user_present": bool(user_id),
        },
    ):
        try:
            result = await operation()
        except AgentException:
            raise
        except Exception as error:
            logger.warning("mcp_tool_failed tool=%s type=%s", name, type(error).__name__)
            raise classify_exception(error, stage=f"mcp.{name}") from error
    return _result(policy=policy, name=name, value=result)


@lru_cache(maxsize=1)
def get_mcp_server() -> FastMCP:
    from app.api.chat import get_orchestrator
    from app.api.try_on import get_try_on_service
    from app.core.virtual_try_on import load_catalog_product

    return create_mcp_server(
        ShoppingMcpService(
            registry_provider=lambda: get_orchestrator().registry,
            product_loader=load_catalog_product,
            try_on_service_provider=get_try_on_service,
            decision_facts_provider=JavaDecisionFactsProvider(),
        )
    )
