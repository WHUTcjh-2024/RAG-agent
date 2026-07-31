from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from PIL import Image, UnidentifiedImageError

from app.core.agent.contracts import SSEEvent
from app.core.agent.errors import AgentException, classify_exception, invalid_input
from app.core.agent.memory import AgentMemoryStore, validate_session_id
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.workflow import (
    RecoverableShoppingAgentWorkflow,
    validate_task_id,
    workflow_enabled,
)
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever


router = APIRouter(tags=["agent"])
logger = logging.getLogger(__name__)
_workflow_guard = Lock()
_workflow_instance: RecoverableShoppingAgentWorkflow | None = None
_workflow_orchestrator: ShoppingAgentOrchestrator | None = None
_workflow_path: str | None = None


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


def get_workflow(
    orchestrator: ShoppingAgentOrchestrator,
) -> RecoverableShoppingAgentWorkflow:
    global _workflow_instance, _workflow_orchestrator, _workflow_path
    configured_path = os.getenv("AGENT_CHECKPOINT_DB_PATH", "").strip()
    with _workflow_guard:
        if (
            _workflow_instance is None
            or _workflow_orchestrator is not orchestrator
            or _workflow_path != configured_path
        ):
            if _workflow_instance is not None:
                _workflow_instance.close()
            _workflow_instance = RecoverableShoppingAgentWorkflow(orchestrator)
            _workflow_orchestrator = orchestrator
            _workflow_path = configured_path
        return _workflow_instance


def reset_workflow() -> None:
    global _workflow_instance, _workflow_orchestrator, _workflow_path
    with _workflow_guard:
        if _workflow_instance is not None:
            _workflow_instance.close()
        _workflow_instance = None
        _workflow_orchestrator = None
        _workflow_path = None


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
    response: Response,
    message: str = Form(default="", max_length=2000),
    session_id: str = Form(default=""),
    task_id: str = Form(default="", max_length=100),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> dict:
    request_id = request.state.request_id
    actual_task_id = validate_task_id(task_id) if task_id.strip() else uuid4().hex
    actual_session_id = (
        validate_session_id(session_id) if session_id.strip() else uuid4().hex
    )
    response.headers["X-Agent-Task-Id"] = actual_task_id
    image_path = await save_upload(file)
    try:
        orchestrator = get_orchestrator()
        if workflow_enabled() and isinstance(
            orchestrator,
            ShoppingAgentOrchestrator,
        ):
            result = await asyncio.to_thread(
                get_workflow(orchestrator).invoke,
                task_id=actual_task_id,
                message=message,
                session_id=actual_session_id,
                image_path=image_path,
                language=language,
                request_id=request_id,
            )
        else:
            result = await asyncio.to_thread(
                orchestrator.handle,
                message,
                actual_session_id,
                image_path,
                language,
                request_id,
            )
            result = result.model_copy(update={"task_id": actual_task_id})
        return result.to_dict()
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
    task_id: str = Form(default="", max_length=100),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> StreamingResponse:
    request_id = request.state.request_id
    actual_task_id = validate_task_id(task_id) if task_id.strip() else uuid4().hex
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
                    "task_id": actual_task_id,
                },
            )
            try:
                orchestrator = get_orchestrator()
                if workflow_enabled() and isinstance(
                    orchestrator,
                    ShoppingAgentOrchestrator,
                ):
                    queue: asyncio.Queue[dict] = asyncio.Queue()
                    loop = asyncio.get_running_loop()

                    def run_workflow() -> None:
                        try:
                            for item in get_workflow(orchestrator).stream(
                                task_id=actual_task_id,
                                message=message,
                                session_id=actual_session_id,
                                image_path=image_path,
                                language=language,
                                request_id=request_id,
                            ):
                                loop.call_soon_threadsafe(queue.put_nowait, item)
                        except Exception as error:
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                {"type": "error", "error": error},
                            )

                    worker = asyncio.create_task(asyncio.to_thread(run_workflow))
                    response = None
                    while response is None:
                        item = await queue.get()
                        if item["type"] == "node":
                            yield sse(SSEEvent.NODE, item["data"])
                        elif item["type"] == "result":
                            response = item["response"]
                        elif item["type"] == "error":
                            raise item["error"]
                    await worker
                else:
                    result = await asyncio.to_thread(
                        orchestrator.handle,
                        message,
                        actual_session_id,
                        image_path,
                        language,
                        request_id,
                    )
                    response = result.model_copy(
                        update={"task_id": actual_task_id}
                    ).to_dict()
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
                    "task_id": response["task_id"],
                    "intent": response["intent"],
                    "slots": response["slots"],
                    "recovered": response["recovered"],
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
                {
                    "ok": True,
                    "request_id": request_id,
                    "task_id": actual_task_id,
                },
            )
        finally:
            remove_upload(image_path)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Agent-Task-Id": actual_task_id,
        },
    )
