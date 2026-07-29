from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError

from app.core.agent.contracts import SSEEvent
from app.core.agent.errors import AgentException, classify_exception, invalid_input
from app.core.agent.memory import AgentMemoryStore, validate_session_id
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever


router = APIRouter(tags=["agent"])
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_memory() -> AgentMemoryStore:
    return AgentMemoryStore()


@lru_cache(maxsize=1)
def get_orchestrator() -> ShoppingAgentOrchestrator:
    data_dir = Path(__file__).resolve().parents[2] / "data" / "vector_store"
    text_index = Path(os.getenv("TEXT_INDEX_DIR", str(data_dir / "text")))
    image_index = Path(os.getenv("IMAGE_INDEX_DIR", str(data_dir / "image")))
    device = os.getenv("IMAGE_DEVICE", "auto")
    text_retriever = TextRetriever(text_index)
    image_retriever = ImageRetriever(image_index, device=device)
    hybrid_retriever = HybridRetriever(text_index, image_index, image_device=device)
    return ShoppingAgentOrchestrator(
        text_retriever=text_retriever,
        image_retriever=image_retriever,
        hybrid_retriever=hybrid_retriever,
        memory=get_memory(),
    )


async def save_upload(file: UploadFile | None) -> str | None:
    if file is None:
        return None
    if file.content_type and not file.content_type.startswith("image/"):
        raise invalid_input("Uploaded file must be an image.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise invalid_input("Uploaded image exceeds 10 MB.", status_code=413)
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise invalid_input("Uploaded file is not a valid image.") from error
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    descriptor, path = tempfile.mkstemp(prefix="shopping-agent-", suffix=suffix)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    return path


def remove_upload(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


@router.post("/chat")
async def chat(
    request: Request,
    message: str = Form(default="", max_length=2000),
    session_id: str = Form(default=""),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> dict:
    request_id = request.state.request_id
    actual_session_id = (
        validate_session_id(session_id) if session_id.strip() else uuid4().hex
    )
    image_path = await save_upload(file)
    try:
        response = await asyncio.to_thread(
            get_orchestrator().handle,
            message,
            actual_session_id,
            image_path,
            language,
            request_id,
        )
        return response.to_dict()
    except AgentException:
        raise
    except Exception as error:
        classified = classify_exception(error, stage="agent")
        logger.warning(
            "agent_request_failed request_id=%s code=%s stage=%s error_type=%s",
            request_id,
            classified.code.value,
            classified.stage,
            type(error).__name__,
        )
        raise classified from error
    finally:
        remove_upload(image_path)


def sse(event: SSEEvent, payload: dict) -> str:
    return (
        f"event: {event.value}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(default="", max_length=2000),
    session_id: str = Form(default=""),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> StreamingResponse:
    request_id = request.state.request_id
    actual_session_id = (
        validate_session_id(session_id) if session_id.strip() else uuid4().hex
    )
    image_path = await save_upload(file)

    async def events():
        try:
            yield sse(
                SSEEvent.STATUS,
                {
                    "state": "processing",
                    "request_id": request_id,
                    "session_id": actual_session_id,
                },
            )
            try:
                result = await asyncio.to_thread(
                    get_orchestrator().handle,
                    message,
                    actual_session_id,
                    image_path,
                    language,
                    request_id,
                )
                response = result.to_dict()
            except Exception as error:
                classified = classify_exception(error, stage="agent")
                logger.warning(
                    "agent_stream_failed request_id=%s code=%s stage=%s error_type=%s",
                    request_id,
                    classified.code.value,
                    classified.stage,
                    type(error).__name__,
                )
                yield sse(
                    SSEEvent.ERROR,
                    classified.to_error(request_id).model_dump(mode="json"),
                )
                return
            yield sse(
                SSEEvent.META,
                {
                    "request_id": response["request_id"],
                    "session_id": response["session_id"],
                    "intent": response["intent"],
                    "slots": response["slots"],
                },
            )
            for trace in response["tool_trace"]:
                yield sse(SSEEvent.TOOL, trace)
            if response["products"]:
                yield sse(SSEEvent.PRODUCTS, {"items": response["products"]})
            if response["comparison"]:
                yield sse(SSEEvent.COMPARISON, {"items": response["comparison"]})
            answer = response["answer"]
            for start in range(0, len(answer), 24):
                yield sse(
                    SSEEvent.MESSAGE,
                    {"delta": answer[start : start + 24]},
                )
                await asyncio.sleep(0)
            yield sse(
                SSEEvent.DONE,
                {"ok": True, "request_id": request_id},
            )
        finally:
            remove_upload(image_path)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
