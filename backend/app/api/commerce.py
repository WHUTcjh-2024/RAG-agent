from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.chat import get_memory, get_orchestrator
from app.core.agent.errors import AgentException, classify_exception
from app.core.agent.memory import validate_session_id

router = APIRouter(tags=["commerce"])


class CompareRequest(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=3)


class SessionRequest(BaseModel):
    session_id: str


def invoke(tool: str, arguments: dict):
    try:
        return get_orchestrator().registry.invoke(tool, arguments)
    except AgentException:
        raise
    except Exception as error:
        raise classify_exception(error, stage="invoke_tool") from error


@router.post("/compare")
def compare(request: Request, payload: CompareRequest) -> dict:
    result = invoke("compare_products", {"product_ids": payload.product_ids})
    return {"request_id": request.state.request_id, **result}


@router.post("/session")
def session_state(request: Request, payload: SessionRequest) -> dict:
    session_id = validate_session_id(payload.session_id)
    memory = get_memory()
    state = memory.get(session_id)
    return {
        "request_id": request.state.request_id,
        "session_id": session_id,
        "slots": dict(state.slots),
        "history": memory.recent_history(session_id, limit=50),
    }
