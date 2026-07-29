from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.chat import get_memory, get_orchestrator
router = APIRouter(tags=["commerce"])


class CompareRequest(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=3)


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)


def invoke(tool: str, arguments: dict):
    try:
        return get_orchestrator().registry.invoke(tool, arguments)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/compare")
def compare(request: CompareRequest) -> dict:
    return invoke("compare_products", {"product_ids": request.product_ids})


@router.post("/session")
def session_state(request: SessionRequest) -> dict:
    memory = get_memory()
    state = memory.get(request.session_id)
    return {
        "session_id": request.session_id,
        "slots": dict(state.slots),
        "history": memory.recent_history(request.session_id, limit=50),
    }
