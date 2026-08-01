from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.agent.decision import DecisionCard


class Intent(str, Enum):
    TEXT_RECOMMENDATION = "text_recommendation"
    IMAGE_SEARCH = "image_search"
    HYBRID_SEARCH = "hybrid_search"
    COMPARE = "compare"
    CART_HANDOFF = "cart_handoff"
    WARDROBE_PLAN = "wardrobe_plan"


class SSEEvent(str, Enum):
    STATUS = "status"
    NODE = "node"
    EVIDENCE = "evidence"
    DECISION = "decision"
    CONFIRM_REQUIRED = "confirm_required"
    WARDROBE_PLAN = "wardrobe_plan"
    META = "meta"
    TOOL = "tool"
    PRODUCTS = "products"
    COMPARISON = "comparison"
    MESSAGE = "message"
    ERROR = "error"
    DONE = "done"


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_SESSION_ID = "INVALID_SESSION_ID"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_TOOL_ARGUMENT = "INVALID_TOOL_ARGUMENT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    BUSINESS_FACT_UNAVAILABLE = "BUSINESS_FACT_UNAVAILABLE"
    TASK_CANCELLED = "TASK_CANCELLED"
    PROMPT_INJECTION_BLOCKED = "PROMPT_INJECTION_BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolTrace(BaseModel):
    tool: str = Field(min_length=1, max_length=100)
    input: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(min_length=1, max_length=500)


class NodeTrace(BaseModel):
    node: str = Field(min_length=1, max_length=100)
    state: str = Field(pattern="^(completed|failed)$")
    duration_ms: float = Field(ge=0)
    summary: str = Field(min_length=1, max_length=500)


class AgentResponse(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=100)
    task_id: str | None = Field(default=None, min_length=1, max_length=100)
    intent: Intent
    answer: str
    products: list[dict[str, Any]] = Field(default_factory=list)
    comparison: list[dict[str, Any]] = Field(default_factory=list)
    slots: dict[str, Any] = Field(default_factory=dict)
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    node_trace: list[NodeTrace] = Field(default_factory=list)
    decision: DecisionCard | None = None
    pending_action: dict[str, Any] | None = None
    wardrobe_plan: dict[str, Any] | None = None
    recovered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentError(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    code: ErrorCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    stage: str = Field(min_length=1, max_length=100)
    details: dict[str, Any] = Field(default_factory=dict)


class AgentErrorEnvelope(BaseModel):
    detail: str
    error: AgentError
