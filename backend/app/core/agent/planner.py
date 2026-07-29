from __future__ import annotations

import os
from typing import Callable

from langchain_openai import ChatOpenAI


TOOL_TO_INTENT = {
    "search_products_by_text": "text_recommendation",
    "search_products_by_image": "image_search",
    "hybrid_search": "hybrid_search",
    "compare_products": "compare",
}


class AgentPlanner:
    """Optional LLM tool selector with a deterministic, offline-safe fallback."""

    def __init__(self, tools: list) -> None:
        if os.getenv("LLM_ENABLED", "true").strip().casefold() not in {"1", "true", "yes"}:
            self.bound = None
            return
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        self.bound = None
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

    def choose(self, message: str, has_image: bool, fallback: Callable[[], str]) -> str:
        if self.bound is None:
            return fallback()
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
                if not has_image and intent in {"image_search", "hybrid_search"}:
                    return fallback()
                if has_image and not message.strip() and intent != "image_search":
                    return fallback()
                return intent
        except Exception:
            pass
        return fallback()
