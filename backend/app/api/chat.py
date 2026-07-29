from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError

from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.memory import AgentMemoryStore
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever


router = APIRouter(tags=["agent"])


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
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds 10 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.") from error
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
    message: str = Form(default="", max_length=2000),
    session_id: str = Form(default="", max_length=100),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> dict:
    actual_session_id = session_id.strip() or uuid4().hex
    image_path = await save_upload(file)
    try:
        response = await asyncio.to_thread(
            get_orchestrator().handle,
            message,
            actual_session_id,
            image_path,
            language,
        )
        return response.to_dict()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        remove_upload(image_path)


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    message: str = Form(default="", max_length=2000),
    session_id: str = Form(default="", max_length=100),
    language: str = Form(default="zh", pattern="^(zh|en)$"),
    file: UploadFile | None = File(default=None),
) -> StreamingResponse:
    actual_session_id = session_id.strip() or uuid4().hex
    image_path = await save_upload(file)

    async def events():
        yield sse("status", {"state": "processing", "session_id": actual_session_id})
        try:
            result = await asyncio.to_thread(
                get_orchestrator().handle,
                message,
                actual_session_id,
                image_path,
                language,
            )
            response = result.to_dict()
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            yield sse("error", {"message": str(error)})
            return
        finally:
            remove_upload(image_path)
        yield sse(
            "meta",
            {
                "session_id": response["session_id"],
                "intent": response["intent"],
                "slots": response["slots"],
            },
        )
        for trace in response["tool_trace"]:
            yield sse("tool", trace)
        if response["products"]:
            yield sse("products", {"items": response["products"]})
        if response["comparison"]:
            yield sse("comparison", {"items": response["comparison"]})
        answer = response["answer"]
        for start in range(0, len(answer), 24):
            yield sse("message", {"delta": answer[start : start + 24]})
            await asyncio.sleep(0)
        yield sse("done", {"ok": True})

    return StreamingResponse(events(), media_type="text/event-stream")
