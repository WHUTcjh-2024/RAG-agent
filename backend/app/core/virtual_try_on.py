from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.catalog_paths import BACKEND_DIR


logger = logging.getLogger(__name__)

TryOnStatus = Literal["QUEUED", "PROCESSING", "SUCCEEDED", "FAILED"]
_SUPPORTED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_MAX_PROVIDER_OUTPUT_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 36_000_000


class TryOnError(Exception):
    """A user-safe virtual try-on error."""

    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderUnavailable(TryOnError):
    def __init__(self, message: str = "Virtual try-on is temporarily unavailable.") -> None:
        super().__init__(message, code="PROVIDER_UNAVAILABLE", retryable=True)


@dataclass(frozen=True)
class VirtualTryOnSettings:
    database_path: Path
    media_dir: Path
    provider_url: str
    provider_api_key: str
    provider_timeout_seconds: float
    result_signing_secret: str
    result_ttl_hours: int
    max_concurrent_jobs: int
    rate_limit_count: int
    rate_limit_window_seconds: int

    @classmethod
    def from_env(cls) -> "VirtualTryOnSettings":
        base_dir = BACKEND_DIR / "data" / "tryon"
        database_path = Path(
            os.getenv("VTO_DB_PATH", str(base_dir / "jobs.db"))
        ).expanduser().resolve()
        media_dir = Path(
            os.getenv("VTO_MEDIA_DIR", str(base_dir / "media"))
        ).expanduser().resolve()
        return cls(
            database_path=database_path,
            media_dir=media_dir,
            provider_url=os.getenv("VTO_PROVIDER_URL", "").strip(),
            provider_api_key=os.getenv("VTO_PROVIDER_API_KEY", "").strip(),
            provider_timeout_seconds=_env_float("VTO_PROVIDER_TIMEOUT_SECONDS", 75, 5, 180),
            result_signing_secret=(
                os.getenv("VTO_RESULT_SIGNING_SECRET", "").strip()
                or os.getenv("AGENT_CONTEXT_TOKEN", "").strip()
                or os.getenv("AGENT_ACTION_SECRET", "").strip()
            ),
            result_ttl_hours=_env_int("VTO_RESULT_TTL_HOURS", 24, 1, 168),
            max_concurrent_jobs=_env_int("VTO_MAX_CONCURRENT_JOBS", 2, 1, 8),
            rate_limit_count=_env_int("VTO_RATE_LIMIT_COUNT", 10, 1, 100),
            rate_limit_window_seconds=_env_int("VTO_RATE_LIMIT_WINDOW_SECONDS", 600, 60, 86_400),
        )


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    width: int
    height: int
    mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class PersonImageAssessment:
    image: PreparedImage
    quality_score: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TryOnJob:
    id: str
    user_id: str
    product_id: str
    category: str
    status: TryOnStatus
    created_at: str
    updated_at: str
    expires_at: str
    attempt_count: int
    input_path: str | None
    output_path: str | None
    image_width: int
    image_height: int
    quality_score: int
    quality_warnings: tuple[str, ...]
    failure_code: str | None


class TryOnStore:
    """Small durable queue for one service instance; suitable for a single worker deployment."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tryon_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    input_path TEXT,
                    output_path TEXT,
                    image_width INTEGER NOT NULL,
                    image_height INTEGER NOT NULL,
                    quality_score INTEGER NOT NULL,
                    quality_warnings_json TEXT NOT NULL,
                    failure_code TEXT,
                    idempotency_key TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tryon_jobs_user_idempotency
                ON tryon_jobs(user_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tryon_jobs_user_created
                ON tryon_jobs(user_id, created_at DESC)
                """
            )

    def find_idempotent(self, user_id: str, idempotency_key: str) -> TryOnJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tryon_jobs WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
        return _job_from_row(row) if row else None

    def create(
        self,
        *,
        user_id: str,
        product_id: str,
        category: str,
        input_path: Path,
        image_width: int,
        image_height: int,
        quality_score: int,
        quality_warnings: tuple[str, ...],
        idempotency_key: str | None,
        rate_limit_count: int,
        rate_limit_window_seconds: int,
        ttl_hours: int,
    ) -> tuple[TryOnJob, bool]:
        now = datetime.now(UTC)
        now_value = _timestamp(now)
        expires_at = _timestamp(now + timedelta(hours=ttl_hours))
        job_id = uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = connection.execute(
                        "SELECT * FROM tryon_jobs WHERE user_id = ? AND idempotency_key = ?",
                        (user_id, idempotency_key),
                    ).fetchone()
                    if existing:
                        connection.execute("COMMIT")
                        return _job_from_row(existing), False
                window_start = _timestamp(now - timedelta(seconds=rate_limit_window_seconds))
                usage = connection.execute(
                    "SELECT COUNT(*) FROM tryon_jobs WHERE user_id = ? AND created_at >= ?",
                    (user_id, window_start),
                ).fetchone()[0]
                if usage >= rate_limit_count:
                    raise TryOnError(
                        "Too many virtual try-on requests. Please try again shortly.",
                        code="RATE_LIMITED",
                        retryable=True,
                    )
                connection.execute(
                    """
                    INSERT INTO tryon_jobs (
                        id, user_id, product_id, category, status, created_at, updated_at,
                        expires_at, attempt_count, input_path, output_path, image_width,
                        image_height, quality_score, quality_warnings_json, failure_code,
                        idempotency_key
                    ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, 0, ?, NULL, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        job_id,
                        user_id,
                        product_id,
                        category,
                        now_value,
                        now_value,
                        expires_at,
                        str(input_path),
                        image_width,
                        image_height,
                        quality_score,
                        json.dumps(quality_warnings, ensure_ascii=False),
                        idempotency_key,
                    ),
                )
                row = connection.execute("SELECT * FROM tryon_jobs WHERE id = ?", (job_id,)).fetchone()
                connection.execute("COMMIT")
                return _job_from_row(row), True
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def get(self, job_id: str, user_id: str) -> TryOnJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tryon_jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
            ).fetchone()
        return _job_from_row(row) if row else None

    def get_unscoped(self, job_id: str) -> TryOnJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tryon_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row) if row else None

    def claim(self, job_id: str) -> TryOnJob | None:
        now = _timestamp(datetime.now(UTC))
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE tryon_jobs
                SET status = 'PROCESSING', attempt_count = attempt_count + 1, updated_at = ?
                WHERE id = ? AND status = 'QUEUED'
                """,
                (now, job_id),
            ).rowcount
            if not updated:
                return None
            row = connection.execute("SELECT * FROM tryon_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row)

    def retry(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tryon_jobs SET status = 'QUEUED', updated_at = ? WHERE id = ?",
                (_timestamp(datetime.now(UTC)), job_id),
            )

    def succeed(self, job_id: str, output_path: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tryon_jobs
                SET status = 'SUCCEEDED', output_path = ?, input_path = NULL,
                    failure_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (str(output_path), _timestamp(datetime.now(UTC)), job_id),
            )

    def fail(self, job_id: str, failure_code: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tryon_jobs
                SET status = 'FAILED', input_path = NULL, failure_code = ?, updated_at = ?
                WHERE id = ?
                """,
                (failure_code, _timestamp(datetime.now(UTC)), job_id),
            )

    def recover_pending(self) -> list[str]:
        """Requeue interrupted work after a process restart."""
        now = _timestamp(datetime.now(UTC))
        with self._connect() as connection:
            connection.execute(
                "UPDATE tryon_jobs SET status = 'QUEUED', updated_at = ? WHERE status = 'PROCESSING'",
                (now,),
            )
            rows = connection.execute(
                "SELECT id FROM tryon_jobs WHERE status = 'QUEUED' ORDER BY created_at ASC"
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def cleanup_expired(self) -> list[Path]:
        now = _timestamp(datetime.now(UTC))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT input_path, output_path FROM tryon_jobs WHERE expires_at <= ?",
                (now,),
            ).fetchall()
            connection.execute("DELETE FROM tryon_jobs WHERE expires_at <= ?", (now,))
        return [Path(value) for row in rows for value in row if value]


def _job_from_row(row: sqlite3.Row) -> TryOnJob:
    warnings = json.loads(row["quality_warnings_json"])
    return TryOnJob(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        product_id=str(row["product_id"]),
        category=str(row["category"]),
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        expires_at=str(row["expires_at"]),
        attempt_count=int(row["attempt_count"]),
        input_path=row["input_path"],
        output_path=row["output_path"],
        image_width=int(row["image_width"]),
        image_height=int(row["image_height"]),
        quality_score=int(row["quality_score"]),
        quality_warnings=tuple(str(item) for item in warnings),
        failure_code=row["failure_code"],
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class HttpVirtualTryOnProvider:
    """Provider adapter for a narrowly-scoped, image-in/image-out inference API."""

    def __init__(self, settings: VirtualTryOnSettings) -> None:
        self.endpoint = settings.provider_url
        self.api_key = settings.provider_api_key
        self.timeout = settings.provider_timeout_seconds

    @property
    def configured(self) -> bool:
        return self.endpoint.startswith("https://") or self.endpoint.startswith("http://127.0.0.1") or self.endpoint.startswith("http://localhost")

    async def render(
        self,
        *,
        person: PreparedImage,
        garment: PreparedImage,
        product_id: str,
        category: str,
        job_id: str,
    ) -> bytes:
        if not self.configured:
            raise ProviderUnavailable("Virtual try-on has not been configured.")
        return await asyncio.to_thread(
            self._render_sync,
            person,
            garment,
            product_id,
            category,
            job_id,
        )

    def _render_sync(
        self,
        person: PreparedImage,
        garment: PreparedImage,
        product_id: str,
        category: str,
        job_id: str,
    ) -> bytes:
        body, boundary = _multipart_body(
            fields={
                "product_id": product_id,
                "category": category,
                "request_id": job_id,
                "prompt": _try_on_prompt(category),
            },
            files={
                "person_image": ("person.jpg", person.mime_type, person.content),
                "garment_image": ("garment.jpg", garment.mime_type, garment.content),
            },
        )
        headers = {
            "Accept": "image/*, application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Request-Id": job_id,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get_content_type()
                payload = response.read(_MAX_PROVIDER_OUTPUT_BYTES + 1)
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or error.code >= 500
            raise TryOnError(
                "Virtual try-on generation failed.",
                code="PROVIDER_REJECTED" if not retryable else "PROVIDER_UNAVAILABLE",
                retryable=retryable,
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ProviderUnavailable() from error
        if len(payload) > _MAX_PROVIDER_OUTPUT_BYTES:
            raise TryOnError("Generated image is too large.", code="INVALID_PROVIDER_RESPONSE")
        if content_type.startswith("image/"):
            return payload
        if content_type == "application/json":
            return _image_from_provider_json(payload)
        raise TryOnError("Provider returned an unsupported response.", code="INVALID_PROVIDER_RESPONSE")


def _multipart_body(
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = "----fitme-" + uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    for name, (filename, mime_type, content) in files.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def _image_from_provider_json(payload: bytes) -> bytes:
    try:
        data = json.loads(payload)
        encoded = data.get("image_base64") or data.get("b64_json")
        if not encoded and isinstance(data.get("data"), list) and data["data"]:
            item = data["data"][0]
            if isinstance(item, dict):
                encoded = item.get("b64_json") or item.get("image_base64")
        if not isinstance(encoded, str):
            raise ValueError("No base64 image payload")
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error) as error:
        raise TryOnError("Provider returned an invalid image.", code="INVALID_PROVIDER_RESPONSE") from error
    if len(image) > _MAX_PROVIDER_OUTPUT_BYTES:
        raise TryOnError("Generated image is too large.", code="INVALID_PROVIDER_RESPONSE")
    return image


def _try_on_prompt(category: str) -> str:
    return (
        "Create a photorealistic virtual try-on image. Keep the same person, face, "
        "body proportions, pose, hands, camera angle and background from person_image. "
        "Dress that person in garment_image as a "
        f"{category}. Preserve garment color, pattern, logo, seams and silhouette. "
        "Render physically plausible drape, folds, occlusion, shadows and fit. "
        "Do not add people, change identity, alter body shape, add text or a watermark."
    )


def prepare_person_image(content: bytes, declared_mime: str | None) -> PersonImageAssessment:
    image = _normalize_image(content, declared_mime, max_long_edge=2048)
    warnings: list[str] = []
    score = 100
    if image.width < 720 or image.height < 960:
        warnings.append("Use a full-body photo at least 720 × 960 for a more reliable result.")
        score -= 25
    ratio = image.height / image.width
    if ratio < 1.15:
        warnings.append("A vertical, head-to-toe photo gives the model better fit context.")
        score -= 20
    if image.width * image.height < 1_000_000:
        warnings.append("Sharper photos improve fabric and edge detail.")
        score -= 10
    return PersonImageAssessment(image=image, quality_score=max(score, 0), warnings=tuple(warnings))


def prepare_garment_image(content: bytes) -> PreparedImage:
    return _normalize_image(content, None, max_long_edge=2048)


def prepare_provider_result(content: bytes) -> PreparedImage:
    return _normalize_image(
        content,
        None,
        max_long_edge=2048,
        max_bytes=_MAX_PROVIDER_OUTPUT_BYTES,
    )


def _normalize_image(
    content: bytes,
    declared_mime: str | None,
    *,
    max_long_edge: int,
    max_bytes: int = _MAX_UPLOAD_BYTES,
) -> PreparedImage:
    if not content:
        raise TryOnError("An image is required.", code="INVALID_IMAGE")
    if len(content) > max_bytes:
        raise TryOnError("Image exceeds the 12 MB limit.", code="IMAGE_TOO_LARGE")
    if declared_mime and declared_mime.casefold() not in _SUPPORTED_IMAGE_MIMES:
        raise TryOnError("Use a JPG, PNG, or WebP image.", code="UNSUPPORTED_IMAGE_TYPE")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            if source.width * source.height > _MAX_IMAGE_PIXELS:
                raise TryOnError("Image dimensions are too large.", code="IMAGE_TOO_LARGE")
            normalized = ImageOps.exif_transpose(source).convert("RGB")
    except TryOnError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise TryOnError("Uploaded file is not a valid image.", code="INVALID_IMAGE") from error
    normalized.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    normalized.save(output, format="JPEG", quality=94, optimize=True)
    return PreparedImage(content=output.getvalue(), width=normalized.width, height=normalized.height)


def infer_category(product: dict[str, object]) -> str:
    source = " ".join(
        str(product.get(field) or "").casefold()
        for field in ("product_type_name", "product_group_name", "garment_group_name", "prod_name")
    )
    categories = (
        ("shoes", ("shoe", "sneaker", "boot", "sandal", "heel")),
        ("dress", ("dress",)),
        ("skirt", ("skirt",)),
        ("bottom", ("trouser", "pants", "jean", "short", "legging")),
        ("outerwear", ("jacket", "coat", "blazer", "cardigan", "vest")),
        ("top", ("shirt", "tee", "t-shirt", "blouse", "sweater", "hoodie", "top", "polo")),
    )
    for category, terms in categories:
        if any(term in source for term in terms):
            return category
    return "apparel"


def validate_idempotency_key(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    key = value.strip()
    if not _IDEMPOTENCY_PATTERN.fullmatch(key):
        raise TryOnError("Idempotency-Key must be 8-128 safe characters.", code="INVALID_IDEMPOTENCY_KEY")
    return key


class VirtualTryOnService:
    def __init__(self, settings: VirtualTryOnSettings, provider: HttpVirtualTryOnProvider | None = None) -> None:
        self.settings = settings
        self.store = TryOnStore(settings.database_path)
        self.provider = provider or HttpVirtualTryOnProvider(settings)
        self.inputs_dir = settings.media_dir / "private-inputs"
        self.outputs_dir = settings.media_dir / "results"
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._scheduled: set[str] = set()
        self._scheduled_lock = threading.Lock()
        self._last_cleanup = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.settings.result_signing_secret and self.provider.configured)

    def submit(
        self,
        *,
        user_id: str,
        product: dict[str, object],
        assessment: PersonImageAssessment,
        idempotency_key: str | None,
    ) -> tuple[TryOnJob, bool]:
        self.cleanup_if_due()
        category = infer_category(product)
        job_id = uuid4().hex
        input_path = self.inputs_dir / f"{job_id}.jpg"
        input_path.write_bytes(assessment.image.content)
        try:
            job, created = self.store.create(
                user_id=user_id,
                product_id=str(product["article_id"]),
                category=category,
                input_path=input_path,
                image_width=assessment.image.width,
                image_height=assessment.image.height,
                quality_score=assessment.quality_score,
                quality_warnings=assessment.warnings,
                idempotency_key=idempotency_key,
                rate_limit_count=self.settings.rate_limit_count,
                rate_limit_window_seconds=self.settings.rate_limit_window_seconds,
                ttl_hours=self.settings.result_ttl_hours,
            )
        except Exception:
            input_path.unlink(missing_ok=True)
            raise
        if not created:
            input_path.unlink(missing_ok=True)
        return job, created

    def schedule(self, job_id: str, product: dict[str, object]) -> None:
        with self._scheduled_lock:
            if job_id in self._scheduled:
                return
            self._scheduled.add(job_id)
        asyncio.create_task(self._run(job_id, product), name=f"try-on-{job_id}")

    async def recover(self) -> None:
        for job_id in self.store.recover_pending():
            job = self.store.get_unscoped(job_id)
            if job is not None:
                try:
                    product = await asyncio.to_thread(load_catalog_product, job.product_id)
                except TryOnError as error:
                    self._fail_job(job, error.code)
                    continue
                self.schedule(job_id, product)

    async def _run(self, job_id: str, product: dict[str, object]) -> None:
        retry_product: dict[str, object] | None = None
        try:
            async with self._semaphore:
                job = self.store.claim(job_id)
                if job is None:
                    return
                try:
                    output = await self.provider.render(
                        person=_prepared_image_from_path(Path(job.input_path or "")),
                        garment=load_product_image(product),
                        product_id=job.product_id,
                        category=job.category,
                        job_id=job.id,
                    )
                    result = prepare_provider_result(output)
                    output_path = self.outputs_dir / f"{job.id}.jpg"
                    output_path.write_bytes(result.content)
                    self.store.succeed(job.id, output_path)
                    Path(job.input_path or "").unlink(missing_ok=True)
                    logger.info("try_on_succeeded job_id=%s category=%s attempt=%s", job.id, job.category, job.attempt_count)
                except TryOnError as error:
                    if error.retryable and job.attempt_count < 3:
                        self.store.retry(job.id)
                        await asyncio.sleep(0.5 * job.attempt_count)
                        retry_product = product
                        return
                    self._fail_job(job, error.code)
                except Exception:
                    logger.exception("try_on_failed job_id=%s", job.id)
                    self._fail_job(job, "INTERNAL_ERROR")
        finally:
            with self._scheduled_lock:
                self._scheduled.discard(job_id)
            if retry_product is not None:
                self.schedule(job_id, retry_product)

    def _fail_job(self, job: TryOnJob, code: str) -> None:
        self.store.fail(job.id, code)
        Path(job.input_path or "").unlink(missing_ok=True)
        logger.warning("try_on_failed job_id=%s code=%s", job.id, code)

    def cleanup_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        for path in self.store.cleanup_expired():
            path.unlink(missing_ok=True)

    def sign_result_url(self, job: TryOnJob) -> str | None:
        if job.status != "SUCCEEDED" or not job.output_path or not self.settings.result_signing_secret:
            return None
        expires_at = int(time.time()) + 15 * 60
        message = f"{job.id}:{job.user_id}:{expires_at}".encode()
        signature = hmac.new(
            self.settings.result_signing_secret.encode(), message, hashlib.sha256
        ).hexdigest()
        return f"/api/try-on/jobs/{job.id}/result?expires={expires_at}&signature={signature}"

    def verify_result_signature(self, job: TryOnJob, expires: int, signature: str) -> bool:
        if expires < int(time.time()) or expires > int(time.time()) + 16 * 60:
            return False
        message = f"{job.id}:{job.user_id}:{expires}".encode()
        expected = hmac.new(
            self.settings.result_signing_secret.encode(), message, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)


def _prepared_image_from_path(path: Path) -> PreparedImage:
    try:
        return prepare_garment_image(path.read_bytes())
    except OSError as error:
        raise TryOnError("Source image is no longer available.", code="INPUT_EXPIRED") from error


def load_product_image(product: dict[str, object]) -> PreparedImage:
    image_path = str(product.get("image_path") or "").replace("\\", "/")
    if not image_path:
        raise TryOnError("This product has no usable try-on image.", code="PRODUCT_IMAGE_UNAVAILABLE")
    from app.core.catalog_paths import get_catalog_image_dir

    image_root = get_catalog_image_dir().resolve()
    relative = Path(image_path)
    if relative.parts and relative.parts[0] == "images":
        relative = Path(*relative.parts[1:])
    candidate = (image_root / relative).resolve()
    if image_root not in candidate.parents or not candidate.is_file():
        raise TryOnError("This product has no usable try-on image.", code="PRODUCT_IMAGE_UNAVAILABLE")
    try:
        return prepare_garment_image(candidate.read_bytes())
    except OSError as error:
        raise TryOnError("This product has no usable try-on image.", code="PRODUCT_IMAGE_UNAVAILABLE") from error


def load_catalog_product(product_id: str) -> dict[str, object]:
    from app.db.database import connect

    try:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT article_id, prod_name, product_type_name, product_group_name,
                       garment_group_name, image_path
                FROM products WHERE article_id = ?
                """,
                (product_id,),
            ).fetchone()
    except FileNotFoundError as error:
        raise TryOnError("Product catalog is temporarily unavailable.", code="CATALOG_UNAVAILABLE", retryable=True) from error
    if row is None:
        raise TryOnError("Product was not found.", code="PRODUCT_NOT_FOUND")
    return dict(row)
