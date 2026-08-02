from __future__ import annotations

import os
from typing import Any, TypedDict

from app.core.agent.errors import invalid_input


TASK_ID_MAX_LENGTH = 100


class AgentState(TypedDict, total=False):
    task_id: str
    request_id: str
    session_id: str
    trusted_user_id: str
    trusted_context: bool
    message: str
    image_path: str | None
    language: str
    input_fingerprint: str
    intent: str
    goal: str
    hard_constraints: dict[str, Any]
    soft_preferences: dict[str, Any]
    context_refs: dict[str, Any]
    candidate_products: list[dict[str, Any]]
    tool_results: dict[str, Any]
    evidence: list[dict[str, Any]]
    missing_fields: list[str]
    fit_risks: list[str]
    confidence: float
    pending_action: dict[str, Any] | None
    executed_nodes: list[str]
    error: dict[str, Any] | None
    slots: dict[str, Any]
    planned_tool: str | None
    planned_arguments: dict[str, Any]
    comparison: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    node_trace: list[dict[str, Any]]
    answer: str
    answer_streamed: bool
    status: str
    response: dict[str, Any]
    decision_product_id: str | None
    decision: dict[str, Any] | None
    wardrobe_snapshot: dict[str, Any] | None
    wardrobe_plan: dict[str, Any] | None


def validate_task_id(task_id: str) -> str:
    candidate = task_id.strip()
    if (
        not candidate
        or len(candidate) > TASK_ID_MAX_LENGTH
        or not all(
            character.isalnum() or character in "._:-" for character in candidate
        )
    ):
        raise invalid_input(
            "Task ID must be 1-100 characters using letters, numbers, '.', '_', ':' or '-'.",
            details={"field": "task_id"},
        )
    return candidate


def workflow_enabled() -> bool:
    return os.getenv("AGENT_WORKFLOW_ENABLED", "true").strip().casefold() in {
        "1",
        "true",
        "yes",
    }
