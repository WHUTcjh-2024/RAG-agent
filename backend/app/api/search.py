from __future__ import annotations

import os
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.text_retriever import TextRetriever


router = APIRouter(tags=["search"])


class TextSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, str | list[str]] = Field(default_factory=dict)


class TextSearchResponse(BaseModel):
    query: str
    total_candidates: int
    pipeline: list[str]
    results: list[dict[str, Any]]


class ImageSearchResponse(BaseModel):
    query_image: str
    total_candidates: int
    results: list[dict[str, Any]]


class HybridSearchResponse(BaseModel):
    query: str
    query_image: str
    total_candidates: int
    pipeline: list[str]
    results: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_text_retriever() -> TextRetriever:
    default_index = (
        Path(__file__).resolve().parents[2] / "data" / "vector_store" / "text"
    )
    index_dir = Path(os.getenv("TEXT_INDEX_DIR", str(default_index)))
    return TextRetriever(index_dir=index_dir)


@lru_cache(maxsize=1)
def get_image_retriever() -> ImageRetriever:
    default_index = (
        Path(__file__).resolve().parents[2] / "data" / "vector_store" / "image"
    )
    index_dir = Path(os.getenv("IMAGE_INDEX_DIR", str(default_index)))
    device = os.getenv("IMAGE_DEVICE", "auto")
    return ImageRetriever(index_dir=index_dir, device=device)


@lru_cache(maxsize=1)
def get_hybrid_retriever() -> HybridRetriever:
    data_dir = Path(__file__).resolve().parents[2] / "data" / "vector_store"
    text_index_dir = Path(os.getenv("TEXT_INDEX_DIR", str(data_dir / "text")))
    image_index_dir = Path(os.getenv("IMAGE_INDEX_DIR", str(data_dir / "image")))
    device = os.getenv("IMAGE_DEVICE", "auto")
    return HybridRetriever(
        text_index_dir=text_index_dir,
        image_index_dir=image_index_dir,
        image_device=device,
    )


@router.post("/search/text", response_model=TextSearchResponse)
def search_text(payload: TextSearchRequest) -> TextSearchResponse:
    try:
        retriever = get_text_retriever()
        results, total_candidates = retriever.search(
            query=payload.query,
            top_k=payload.top_k,
            filters=payload.filters,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return TextSearchResponse(
        query=payload.query,
        total_candidates=total_candidates,
        pipeline=["dense", "bm25", "rrf", "rerank"],
        results=results,
    )


@router.post("/search/image", response_model=ImageSearchResponse)
async def search_image(
    file: UploadFile = File(...),
    top_k: int = Form(default=10, ge=1, le=100),
    filters: str = Form(default="{}"),
) -> ImageSearchResponse:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")
    try:
        parsed_filters = json.loads(filters)
        if not isinstance(parsed_filters, dict):
            raise ValueError("filters must be a JSON object")
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=400, detail=f"Invalid filters JSON: {error}"
        ) from error

    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds 10 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = source.convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a valid image."
        ) from error

    try:
        retriever = get_image_retriever()
        results, total_candidates = retriever.search(
            image=image,
            top_k=top_k,
            filters=parsed_filters,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return ImageSearchResponse(
        query_image=file.filename or "uploaded-image",
        total_candidates=total_candidates,
        results=results,
    )


@router.post("/search/hybrid", response_model=HybridSearchResponse)
async def search_hybrid(
    query: str = Form(..., min_length=1, max_length=500),
    file: UploadFile = File(...),
    top_k: int = Form(default=10, ge=1, le=100),
    filters: str = Form(default="{}"),
) -> HybridSearchResponse:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")
    try:
        parsed_filters = json.loads(filters)
        if not isinstance(parsed_filters, dict):
            raise ValueError("filters must be a JSON object")
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=400, detail=f"Invalid filters JSON: {error}"
        ) from error

    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds 10 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = source.convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a valid image."
        ) from error

    try:
        retriever = get_hybrid_retriever()
        results, total_candidates = retriever.search(
            query=query,
            image=image,
            top_k=top_k,
            filters=parsed_filters,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return HybridSearchResponse(
        query=query,
        query_image=file.filename or "uploaded-image",
        total_candidates=total_candidates,
        pipeline=["dense", "bm25", "image", "rrf", "rerank"],
        results=results,
    )
