from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core.virtual_try_on import (
    TryOnError,
    TryOnJob,
    VirtualTryOnService,
    VirtualTryOnSettings,
    load_catalog_product,
    prepare_person_image,
    validate_idempotency_key,
)


router = APIRouter(tags=["virtual-try-on"])
_CONTEXT_TOKEN_HEADER = "X-Agent-Context-Token"


def _normalized_mime(value: str | None) -> str | None:
    mime_type = (value or "").strip().casefold()
    return "image/jpeg" if mime_type == "image/jpg" else mime_type or None


@lru_cache(maxsize=1)
def get_try_on_service() -> VirtualTryOnService:
    return VirtualTryOnService(VirtualTryOnSettings.from_env())


def _trusted_user_id(request: Request) -> str:
    expected_token = os.getenv("VTO_CONTEXT_TOKEN", "").strip() or os.getenv(
        "AGENT_CONTEXT_TOKEN", ""
    ).strip()
    user_id = request.headers.get("X-Trusted-User-Id", "").strip()
    if not expected_token or not user_id or request.headers.get(_CONTEXT_TOKEN_HEADER) != expected_token:
        raise HTTPException(status_code=401, detail="Please sign in to use virtual try-on.")
    return user_id


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
        "photo_quality": {
            "score": job.quality_score,
            "warnings": list(job.quality_warnings),
        },
        "result": {"url": result_url} if result_url else None,
        "failure": {"code": job.failure_code} if job.status == "FAILED" else None,
    }


@router.post("/try-on/jobs", status_code=202)
async def create_try_on_job(
    request: Request,
    product_id: str = Form(..., min_length=1, max_length=100),
    person_image: UploadFile = File(...),
    consent: bool = Form(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    user_id = _trusted_user_id(request)
    if not consent:
        raise HTTPException(
            status_code=422,
            detail="Consent is required before processing a personal photo.",
        )
    service = get_try_on_service()
    if not service.configured:
        raise HTTPException(status_code=503, detail="Virtual try-on has not been configured.")
    try:
        normalized_key = validate_idempotency_key(idempotency_key)
        if normalized_key:
            existing = service.store.find_idempotent(user_id, normalized_key)
            if existing is not None:
                return JSONResponse(status_code=200, content=_job_payload(service, existing))
        content = await person_image.read(12 * 1024 * 1024 + 1)
        assessment = prepare_person_image(content, _normalized_mime(person_image.content_type))
        product = await asyncio.to_thread(load_catalog_product, product_id.strip())
        job, created = service.submit(
            user_id=user_id,
            product=product,
            assessment=assessment,
            idempotency_key=normalized_key,
        )
    except TryOnError as error:
        _raise_try_on_error(error)
    if created:
        service.schedule(job.id, product)
    return JSONResponse(
        status_code=202 if created else 200,
        content=_job_payload(service, job),
        headers={"Retry-After": "2"} if created else {},
    )


@router.get("/try-on/jobs/{job_id}")
def get_try_on_job(job_id: str, request: Request) -> dict[str, object]:
    user_id = _trusted_user_id(request)
    service = get_try_on_service()
    service.cleanup_if_due()
    job = service.store.get(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Virtual try-on job was not found.")
    return _job_payload(service, job)


@router.get("/try-on/jobs/{job_id}/result")
def get_try_on_result(
    job_id: str,
    expires: int = Query(..., ge=0),
    signature: str = Query(..., min_length=32, max_length=128),
) -> FileResponse:
    service = get_try_on_service()
    service.cleanup_if_due()
    job = service.store.get_unscoped(job_id)
    if job is None or not service.verify_result_signature(job, expires, signature):
        raise HTTPException(status_code=404, detail="Virtual try-on result was not found.")
    path = Path(job.output_path or "")
    if job.status != "SUCCEEDED" or not path.is_file():
        raise HTTPException(status_code=404, detail="Virtual try-on result was not found.")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
