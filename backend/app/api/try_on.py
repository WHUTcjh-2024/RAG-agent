from __future__ import annotations

import asyncio
import json
import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.core.virtual_try_on import (
    SyntheticBodyProfile,
    TryOnError,
    TryOnJob,
    VirtualTryOnService,
    build_virtual_try_on_service,
    infer_category,
    load_catalog_product,
    load_product_image,
    validate_idempotency_key,
)


router = APIRouter(tags=["virtual-try-on"])
internal_router = APIRouter(tags=["internal"])
_CONTEXT_TOKEN_HEADER = "X-Agent-Context-Token"


class BodyProfileRequest(BaseModel):
    height_cm: float = Field(ge=135, le=220)
    weight_kg: float = Field(ge=30, le=220)
    chest_cm: float = Field(ge=60, le=170)
    waist_cm: float = Field(ge=45, le=180)
    hip_cm: float = Field(ge=60, le=180)
    shoulder_cm: float | None = Field(default=None, ge=28, le=70)
    inseam_cm: float | None = Field(default=None, ge=45, le=120)
    presentation: Literal["FEMININE", "MASCULINE", "NEUTRAL"] = "NEUTRAL"
    body_shape: Literal["BALANCED", "TRIANGLE", "INVERTED_TRIANGLE", "RECTANGLE", "OVAL"] = "BALANCED"
    skin_tone: Literal["LIGHT", "MEDIUM", "TAN", "DEEP"] = "MEDIUM"
    fit_preference: Literal["CLOSE", "REGULAR", "RELAXED"] = "REGULAR"

    @model_validator(mode="after")
    def validate_proportions(self) -> BodyProfileRequest:
        bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
        if bmi < 10 or bmi > 70:
            raise ValueError("身高和体重组合超出可生成范围")
        return self

    def to_domain(self) -> SyntheticBodyProfile:
        return SyntheticBodyProfile.from_dict(self.model_dump())


class CreateTryOnRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    body_profile: BodyProfileRequest


class SaveTryOnRequest(BaseModel):
    saved: bool = True


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    issues: list[
        Literal[
            "BODY_PROPORTION",
            "GARMENT_DETAIL",
            "MATERIAL",
            "COLOR",
            "OCCLUSION",
            "OTHER",
        ]
    ] = Field(default_factory=list, max_length=5)


class InternalRenderRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    body_profile: BodyProfileRequest


@lru_cache(maxsize=1)
def get_try_on_service() -> VirtualTryOnService:
    return build_virtual_try_on_service()


def _trusted_user_id(request: Request) -> str:
    expected_token = os.getenv("VTO_CONTEXT_TOKEN", "").strip() or os.getenv(
        "AGENT_CONTEXT_TOKEN", ""
    ).strip()
    user_id = request.headers.get("X-Trusted-User-Id", "").strip()
    if not expected_token or not user_id or request.headers.get(_CONTEXT_TOKEN_HEADER) != expected_token:
        raise HTTPException(status_code=401, detail="请登录后使用虚拟试穿。")
    return user_id


def _require_internal_token(request: Request) -> None:
    expected_token = os.getenv("AGENT_INTERNAL_TOKEN", "").strip()
    supplied_token = request.headers.get("X-Agent-Internal-Token", "")
    if not expected_token or supplied_token != expected_token:
        raise HTTPException(status_code=401, detail="Internal authentication required.")


def _raise_try_on_error(error: TryOnError) -> None:
    status = {
        "RATE_LIMITED": 429,
        "IMAGE_TOO_LARGE": 413,
        "PROVIDER_UNAVAILABLE": 503,
        "CATALOG_UNAVAILABLE": 503,
        "PRODUCT_NOT_FOUND": 404,
    }.get(error.code, 422)
    headers = {"Retry-After": "60"} if error.code == "RATE_LIMITED" else None
    raise HTTPException(status_code=status, detail=error.args[0], headers=headers)


@internal_router.post("/internal/try-on/render", include_in_schema=False)
async def render_try_on_for_scheduler(
    payload: InternalRenderRequest,
    request: Request,
) -> Response:
    """Private inference bridge used by the Java scheduler; never expose it through the gateway."""
    _require_internal_token(request)
    service = get_try_on_service()
    if not service.configured:
        raise HTTPException(status_code=503, detail="Try-on inference is not configured.")
    try:
        product = await asyncio.to_thread(load_catalog_product, payload.product_id.strip())
        output = await service.provider.render(
            body_profile=payload.body_profile.to_domain(),
            garment=await asyncio.to_thread(load_product_image, product),
            product_id=payload.product_id.strip(),
            category=infer_category(product),
            job_id=payload.job_id,
        )
    except TryOnError as error:
        _raise_try_on_error(error)
    return Response(content=output, media_type="image/jpeg")


def _job_payload(service: VirtualTryOnService, job: TryOnJob) -> dict[str, object]:
    result_url = service.sign_result_url(job)
    return {
        "id": job.id,
        "product_id": job.product_id,
        "category": job.category,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "expires_at": job.expires_at,
        "retry_after_seconds": 2 if job.status in {"QUEUED", "PROCESSING"} else None,
        "attempt_count": job.attempt_count,
        "model": {
            "kind": "SYNTHETIC_ADULT",
            "body_profile": job.body_profile.to_dict(),
            "uses_person_photo": False,
        },
        "result": {"url": result_url} if result_url else None,
        "failure": {"code": job.failure_code} if job.status == "FAILED" else None,
        "saved": job.saved,
        "feedback": json.loads(job.feedback) if job.feedback else None,
    }


@router.post("/try-on/jobs", status_code=202)
async def create_try_on_job(
    payload: CreateTryOnRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    if not service.configured:
        raise HTTPException(status_code=503, detail="当前环境尚未配置虚拟模特生成服务。")
    try:
        normalized_key = validate_idempotency_key(idempotency_key)
        if normalized_key:
            existing = service.store.find_idempotent(user_id, normalized_key)
            if existing is not None:
                return _json_response(200, _job_payload(service, existing))
        product = await asyncio.to_thread(load_catalog_product, payload.product_id.strip())
        job, created = service.submit(
            user_id=user_id,
            product=product,
            body_profile=payload.body_profile.to_domain(),
            idempotency_key=normalized_key,
        )
    except TryOnError as error:
        _raise_try_on_error(error)
    if created:
        await service.dispatch(job.id)
    return _json_response(
        202 if created else 200,
        _job_payload(service, job),
        headers={"Retry-After": "2"} if created else None,
    )


@router.get("/try-on/jobs")
def list_try_on_jobs(
    request: Request,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, object]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    service.cleanup_if_due()
    return {"items": [_job_payload(service, job) for job in service.store.list_user(user_id, limit)]}


@router.get("/try-on/jobs/{job_id}")
def get_try_on_job(job_id: str, request: Request) -> dict[str, object]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    service.cleanup_if_due()
    job = service.store.get(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="未找到该试穿任务。")
    return _job_payload(service, job)


@router.post("/try-on/jobs/{job_id}/save")
def save_try_on_job(job_id: str, payload: SaveTryOnRequest, request: Request) -> dict[str, object]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    ttl = service.settings.saved_result_ttl_hours if payload.saved else service.settings.result_ttl_hours
    job = service.store.set_saved(job_id, user_id, payload.saved, ttl)
    if job is None:
        raise HTTPException(status_code=404, detail="未找到可保存的试穿结果。")
    return _job_payload(service, job)


@router.post("/try-on/jobs/{job_id}/feedback")
def feedback_try_on_job(job_id: str, payload: FeedbackRequest, request: Request) -> dict[str, object]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    feedback = json.dumps(payload.model_dump(), separators=(",", ":"))
    job = service.store.set_feedback(job_id, user_id, feedback)
    if job is None:
        raise HTTPException(status_code=404, detail="未找到该试穿结果。")
    return _job_payload(service, job)


@router.post("/try-on/jobs/{job_id}/share")
def share_try_on_job(job_id: str, request: Request) -> dict[str, str]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    job = service.store.get(job_id, user_id)
    url = service.sign_result_url(job) if job else None
    if not url:
        raise HTTPException(status_code=404, detail="未找到可分享的试穿结果。")
    return {"url": url}


@router.delete("/try-on/jobs/{job_id}", status_code=204)
def delete_try_on_job(job_id: str, request: Request) -> Response:
    user_id = _trusted_user_id(request)
    if not get_try_on_service().delete(job_id, user_id):
        raise HTTPException(status_code=404, detail="未找到该试穿结果。")
    return Response(status_code=204)


@router.get("/try-on/jobs/{job_id}/result")
def get_try_on_result(
    job_id: str,
    expires: int = Query(..., ge=0),
    signature: str = Query(..., min_length=32, max_length=128),
) -> Response:
    service = get_try_on_service()
    service.cleanup_if_due()
    job = service.store.get_unscoped(job_id)
    if job is None or not service.verify_result_signature(job, expires, signature):
        raise HTTPException(status_code=404, detail="未找到该试穿结果。")
    if job.status != "SUCCEEDED" or not job.output_key:
        raise HTTPException(status_code=404, detail="未找到该试穿结果。")
    content = service.media_store.read(job.output_key)
    if content is None:
        raise HTTPException(status_code=404, detail="未找到该试穿结果。")
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-AI-Generated": "synthetic-virtual-model",
        },
    )


def _json_response(status_code: int, content: dict[str, object], headers: dict[str, str] | None = None) -> Response:
    return Response(
        content=json.dumps(content, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
        headers=headers,
    )
