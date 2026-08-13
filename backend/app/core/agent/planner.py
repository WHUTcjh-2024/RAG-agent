from __future__ import annotations

import logging
import os
from typing import Callable, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.agent.contracts import ErrorCode, Intent
from app.core.request_id import current_request_id


TOOL_TO_INTENT = {
    "search_products_by_text": Intent.TEXT_RECOMMENDATION,
    "search_products_by_image": Intent.IMAGE_SEARCH,
    "hybrid_search": Intent.HYBRID_SEARCH,
    "compare_products": Intent.COMPARE,
}
logger = logging.getLogger(__name__)
REACT_TOOL_NAMES = frozenset(
    {
        "search_products_by_text",
        "search_products_by_image",
        "hybrid_search",
        "get_product_detail",
        "compare_products",
    }
)
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "developer message",
    "call a tool",
    "忽略之前的指令",
    "忽略所有指令",
    "系统提示词",
    "调用工具",
)


class ReActDecision(BaseModel):
    """A bounded action decision; private reasoning is never returned to clients."""

    action: Literal["tool", "finish"]
    tool: str | None = None
    query: str | None = Field(default=None, max_length=2_000)
    product_ids: list[str] = Field(default_factory=list, max_length=3)


class AgentPlanner:
    """Optional LLM tool selector with a deterministic, offline-safe fallback."""

    def __init__(self, tools: list) -> None:
        self.bound = None
        self.reactor = None
        if os.getenv("LLM_ENABLED", "true").strip().casefold() not in {"1", "true", "yes"}:
            return
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        if api_key and model:
            llm = ChatOpenAI(
                api_key=api_key,
                model=model,
                base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
                temperature=0,
                max_retries=1,
                request_timeout=30,
                extra_body={
                    "thinking": {"type": os.getenv("LLM_THINKING", "disabled")}
                },
            )
            action_tools = [tool for tool in tools if tool.name in TOOL_TO_INTENT]
            self.bound = llm.bind_tools(action_tools, tool_choice="required")
            self.reactor = llm.with_structured_output(ReActDecision)

    def choose(
        self,
        message: str,
        has_image: bool,
        fallback: Callable[[], Intent],
    ) -> Intent:
        fallback_intent = fallback()
        if any(marker in message.casefold() for marker in PROMPT_INJECTION_MARKERS):
            logger.warning(
                "agent_prompt_injection_blocked request_id=%s stage=plan_tools",
                current_request_id(),
            )
            return fallback_intent
        if fallback_intent in {Intent.CART_HANDOFF, Intent.COMPARE, Intent.WARDROBE_PLAN}:
            return fallback_intent
        if self.bound is None:
            return fallback_intent
        try:
            response = self.bound.invoke(
                [
                    (
                        "system",
                        "Select exactly one shopping tool. An uploaded image is "
                        f"{'present' if has_image else 'absent'}. Do not invent product IDs.",
                    ),
                    ("human", message or "Find products similar to the uploaded image."),
                ]
            )
            calls = getattr(response, "tool_calls", [])
            if calls and calls[0].get("name") in TOOL_TO_INTENT:
                intent = TOOL_TO_INTENT[calls[0]["name"]]
                if not has_image and intent in {
                    Intent.IMAGE_SEARCH,
                    Intent.HYBRID_SEARCH,
                }:
                    return fallback_intent
                if (
                    has_image
                    and fallback_intent in {
                        Intent.IMAGE_SEARCH,
                        Intent.HYBRID_SEARCH,
                    }
                    and intent != fallback_intent
                ):
                    return fallback_intent
                return intent
        except Exception as error:
            logger.warning(
                "agent_model_fallback request_id=%s code=%s stage=plan_tools error_type=%s",
                current_request_id(),
                ErrorCode.MODEL_UNAVAILABLE.value,
                type(error).__name__,
            )
        return fallback_intent

    def replan(
        self,
        *,
        message: str,
        has_image: bool,
        observations: list[dict],
        allowed_tools: set[str],
        fallback: Callable[[], ReActDecision],
    ) -> ReActDecision:
        """Choose the next tool from observations, with a deterministic fallback."""
        fallback_decision = fallback()
        if self.reactor is None or any(
            marker in message.casefold() for marker in PROMPT_INJECTION_MARKERS
        ):
            return fallback_decision
        safe_tools = sorted(REACT_TOOL_NAMES & allowed_tools)
        if not safe_tools:
            return ReActDecision(action="finish")
        try:
            decision = self.reactor.invoke(
                [
                    (
                        "system",
                        "You are a shopping ReAct planner. Based only on the user request "
                        "and tool observations, either finish or select one next tool. Never "
                        "invent product IDs. Do not call an image tool when no image is present. "
                        f"Allowed tools: {', '.join(safe_tools)}. Image present: {has_image}. "
                        "Finish once the evidence is sufficient.",
                    ),
                    ("human", {"request": message, "observations": observations[-3:]}),
                ]
            )
            if decision.action == "finish":
                return decision
            if decision.tool in safe_tools:
                if not has_image and decision.tool in {
                    "search_products_by_image",
                    "hybrid_search",
                }:
                    return fallback_decision
                return decision
        except Exception as error:
            logger.warning(
                "agent_model_fallback request_id=%s code=%s stage=react_replan error_type=%s",
                current_request_id(),
                ErrorCode.MODEL_UNAVAILABLE.value,
                type(error).__name__,
            )
        return fallback_decision
