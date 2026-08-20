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
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from opentelemetry import metrics
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg import Error as PgError

from app.core.catalog_paths import BACKEND_DIR
from app.db.pg import PgConnection, connect as _pg_connect


logger = logging.getLogger(__name__)
meter = metrics.get_meter("app.virtual_try_on")
submitted_counter = meter.create_counter("vto.jobs.submitted")
completed_counter = meter.create_counter("vto.jobs.completed")
provider_latency = meter.create_histogram("vto.provider.duration", unit="s")
queue_latency = meter.create_histogram("vto.queue.duration", unit="s")

TryOnStatus = Literal["QUEUED", "PROCESSING", "SUCCEEDED", "FAILED"]
Presentation = Literal["FEMININE", "MASCULINE", "NEUTRAL"]
BodyShape = Literal["BALANCED", "TRIANGLE", "INVERTED_TRIANGLE", "RECTANGLE", "OVAL"]
SkinTone = Literal["LIGHT", "MEDIUM", "TAN", "DEEP"]
FitPreference = Literal["CLOSE", "REGULAR", "RELAXED"]

_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_MAX_PROVIDER_OUTPUT_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 36_000_000


class TryOnError(Exception):
    """A stable, user-safe virtual try-on error."""

    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderUnavailable(TryOnError):
    def __init__(self, message: str = "虚拟试穿服务暂时不可用，请稍后重试。") -> None:
        super().__init__(message, code="PROVIDER_UNAVAILABLE", retryable=True)


@dataclass(frozen=True)
class SyntheticBodyProfile:
    height_cm: float
    weight_kg: float
    chest_cm: float
    waist_cm: float
    hip_cm: float
    shoulder_cm: float | None = None
    inseam_cm: float | None = None
    presentation: Presentation = "NEUTRAL"
    body_shape: BodyShape = "BALANCED"
    skin_tone: SkinTone = "MEDIUM"
    fit_preference: FitPreference = "REGULAR"

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> SyntheticBodyProfile:
        return cls(
            height_cm=float(value["height_cm"]),
            weight_kg=float(value["weight_kg"]),
            chest_cm=float(value["chest_cm"]),
            waist_cm=float(value["waist_cm"]),
            hip_cm=float(value["hip_cm"]),
            shoulder_cm=_optional_float(value.get("shoulder_cm")),
            inseam_cm=_optional_float(value.get("inseam_cm")),
            presentation=str(value.get("presentation", "NEUTRAL")),  # type: ignore[arg-type]
            body_shape=str(value.get("body_shape", "BALANCED")),  # type: ignore[arg-type]
            skin_tone=str(value.get("skin_tone", "MEDIUM")),  # type: ignore[arg-type]
            fit_preference=str(value.get("fit_preference", "REGULAR")),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True)
class VirtualTryOnSettings:
    media_dir: Path
    provider_url: str
    provider_api_key: str
    provider_timeout_seconds: float
    result_signing_secret: str
    result_ttl_hours: int
    saved_result_ttl_hours: int
    max_concurrent_jobs: int
    rate_limit_count: int
    rate_limit_window_seconds: int
    database_url: str = ""
    redis_url: str = ""
    redis_prefix: str = "fitme:vto"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    @classmethod
    def from_env(cls) -> VirtualTryOnSettings:
        base_dir = BACKEND_DIR / "data" / "tryon"
        return cls(
            database_url=os.getenv("VTO_DATABASE_URL", "").strip(),
            media_dir=Path(os.getenv("VTO_MEDIA_DIR", str(base_dir / "media"))).expanduser().resolve(),
            provider_url=os.getenv("VTO_PROVIDER_URL", "").strip(),
            provider_api_key=os.getenv("VTO_PROVIDER_API_KEY", "").strip(),
            provider_timeout_seconds=_env_float("VTO_PROVIDER_TIMEOUT_SECONDS", 75, 5, 180),
            result_signing_secret=(
                os.getenv("VTO_RESULT_SIGNING_SECRET", "").strip()
                or os.getenv("AGENT_CONTEXT_TOKEN", "").strip()
                or os.getenv("AGENT_ACTION_SECRET", "").strip()
            ),
            result_ttl_hours=_env_int("VTO_RESULT_TTL_HOURS", 24, 1, 168),
            saved_result_ttl_hours=_env_int("VTO_SAVED_RESULT_TTL_HOURS", 168, 24, 720),
            max_concurrent_jobs=_env_int("VTO_MAX_CONCURRENT_JOBS", 2, 1, 16),
            rate_limit_count=_env_int("VTO_RATE_LIMIT_COUNT", 10, 1, 100),
            rate_limit_window_seconds=_env_int("VTO_RATE_LIMIT_WINDOW_SECONDS", 600, 60, 86_400),
            redis_url=os.getenv("VTO_REDIS_URL", "").strip(),
            redis_prefix=os.getenv("VTO_REDIS_PREFIX", "fitme:vto").strip() or "fitme:vto",
            s3_endpoint_url=os.getenv("VTO_S3_ENDPOINT_URL", "").strip(),
            s3_bucket=os.getenv("VTO_S3_BUCKET", "").strip(),
            s3_region=os.getenv("VTO_S3_REGION", "us-east-1").strip() or "us-east-1",
            s3_access_key=os.getenv("VTO_S3_ACCESS_KEY", "").strip(),
            s3_secret_key=os.getenv("VTO_S3_SECRET_KEY", "").strip(),
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
class TryOnJob:
    id: str
    user_id: str
    product_id: str
    category: str
    body_profile: SyntheticBodyProfile
    status: TryOnStatus
    created_at: str
    updated_at: str
    expires_at: str
    attempt_count: int
    output_key: str | None
    failure_code: str | None
    saved: bool = False
    feedback: str | None = None


class JobStore(Protocol):
    def find_idempotent(self, user_id: str, idempotency_key: str) -> TryOnJob | None: ...

    def create(
        self,
        *,
        user_id: str,
        product_id: str,
        category: str,
        body_profile: SyntheticBodyProfile,
        idempotency_key: str | None,
        rate_limit_count: int,
        rate_limit_window_seconds: int,
        ttl_hours: int,
    ) -> tuple[TryOnJob, bool]: ...

    def get(self, job_id: str, user_id: str) -> TryOnJob | None: ...
    def get_unscoped(self, job_id: str) -> TryOnJob | None: ...
    def claim(self, job_id: str) -> TryOnJob | None: ...
    def retry(self, job_id: str) -> None: ...
    def succeed(self, job_id: str, output_key: str) -> None: ...
    def fail(self, job_id: str, failure_code: str) -> None: ...
    def list_user(self, user_id: str, limit: int) -> list[TryOnJob]: ...
    def set_saved(self, job_id: str, user_id: str, saved: bool, ttl_hours: int) -> TryOnJob | None: ...
    def set_feedback(self, job_id: str, user_id: str, feedback: str) -> TryOnJob | None: ...
    def delete(self, job_id: str, user_id: str) -> TryOnJob | None: ...
    def recover_pending(self) -> list[str]: ...
    def cleanup_expired(self) -> list[str]: ...


class MediaStore(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def read(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...


class JobDispatcher(Protocol):
    distributed: bool

    async def enqueue(self, job_id: str) -> None: ...
    async def next(self, timeout_seconds: int = 5) -> str | None: ...
    async def ack(self, job_id: str) -> None: ...
    async def recover(self) -> None: ...


class PostgresTryOnStore:
    """PostgreSQL-backed job store for the virtual try-on pipeline."""

    def __init__(self, settings: VirtualTryOnSettings) -> None:
        self._database_url = settings.database_url
        if not self._database_url:
            raise RuntimeError("VTO_DATABASE_URL is required for the PostgreSQL try-on store.")
        self._initialize()

    def _connect(self) -> PgConnection:
        return _pg_connect("VTO_DATABASE_URL", default=self._database_url)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tryon_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    input_path TEXT,
                    output_path TEXT,
                    image_width INTEGER NOT NULL DEFAULT 0,
                    image_height INTEGER NOT NULL DEFAULT 0,
                    quality_score INTEGER NOT NULL DEFAULT 100,
                    quality_warnings_json TEXT NOT NULL DEFAULT '[]',
                    failure_code TEXT,
                    idempotency_key TEXT,
                    body_profile_json TEXT NOT NULL DEFAULT '{}',
                    saved INTEGER NOT NULL DEFAULT 0,
                    feedback TEXT
                )
                """
            )
            existing = {
                str(row["column_name"])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'tryon_jobs'"
                )
            }
            for name, definition in (
                ("body_profile_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("saved", "INTEGER NOT NULL DEFAULT 0"),
                ("feedback", "TEXT"),
            ):
                if name not in existing:
                    connection.execute(f"ALTER TABLE tryon_jobs ADD COLUMN {name} {definition}")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tryon_jobs_user_idempotency "
                "ON tryon_jobs(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tryon_jobs_user_created "
                "ON tryon_jobs(user_id, created_at DESC)"
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
        body_profile: SyntheticBodyProfile,
        idempotency_key: str | None,
        rate_limit_count: int,
        rate_limit_window_seconds: int,
        ttl_hours: int,
    ) -> tuple[TryOnJob, bool]:
        now = datetime.now(UTC)
        now_value = now
        job_id = uuid4().hex
        with self._connect() as connection:
            # SQLite previously used a database-wide immediate write lock here.
            # Serializing only this user's transaction preserves strict rate limits
            # and idempotency without penalizing unrelated users on Postgres.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                (f"tryon:{user_id}",),
            )
            if idempotency_key:
                row = connection.execute(
                    "SELECT * FROM tryon_jobs WHERE user_id = ? AND idempotency_key = ?",
                    (user_id, idempotency_key),
                ).fetchone()
                if row:
                    return _job_from_row(row), False
            window_start = now - timedelta(seconds=rate_limit_window_seconds)
            usage = connection.execute(
                "SELECT COUNT(*) FROM tryon_jobs WHERE user_id = ? AND created_at >= ?",
                (user_id, window_start),
            ).fetchone()[0]
            if usage >= rate_limit_count:
                raise TryOnError("试穿次数过多，请稍后再试。", code="RATE_LIMITED", retryable=True)
            expires_at = now + timedelta(hours=ttl_hours)
            connection.execute(
                """
                INSERT INTO tryon_jobs (
                    id, user_id, product_id, category, status, created_at, updated_at,
                    expires_at, attempt_count, input_path, output_path, image_width,
                    image_height, quality_score, quality_warnings_json, failure_code,
                    idempotency_key, body_profile_json, saved, feedback
                ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, 0, NULL, NULL, 0, 0, 100, '[]', NULL, ?, ?, 0, NULL)
                """,
                (
                    job_id,
                    user_id,
                    product_id,
                    category,
                    now_value,
                    now_value,
                    expires_at,
                    idempotency_key,
                    json.dumps(body_profile.to_dict(), ensure_ascii=False, separators=(",", ":")),
                ),
            )
            row = connection.execute("SELECT * FROM tryon_jobs WHERE id = ?", (job_id,)).fetchone()
            return _job_from_row(row), True

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
        now = datetime.now(UTC)
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE tryon_jobs SET status = 'PROCESSING', attempt_count = attempt_count + 1, "
                "updated_at = ? WHERE id = ? AND status = 'QUEUED'",
                (now, job_id),
            ).rowcount
            row = connection.execute("SELECT * FROM tryon_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row) if updated and row else None

    def retry(self, job_id: str) -> None:
        self._update(job_id, "status = 'QUEUED', updated_at = ?", (datetime.now(UTC),))

    def succeed(self, job_id: str, output_key: str) -> None:
        self._update(
            job_id,
            "status = 'SUCCEEDED', output_path = ?, failure_code = NULL, updated_at = ?",
            (output_key, datetime.now(UTC)),
        )

    def fail(self, job_id: str, failure_code: str) -> None:
        self._update(
            job_id,
            "status = 'FAILED', failure_code = ?, updated_at = ?",
            (failure_code, datetime.now(UTC)),
        )

    def _update(self, job_id: str, clause: str, values: tuple[object, ...]) -> None:
        with self._connect() as connection:
            connection.execute(f"UPDATE tryon_jobs SET {clause} WHERE id = ?", (*values, job_id))

    def list_user(self, user_id: str, limit: int) -> list[TryOnJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tryon_jobs WHERE user_id = ? AND expires_at > ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, datetime.now(UTC), limit),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def set_saved(self, job_id: str, user_id: str, saved: bool, ttl_hours: int) -> TryOnJob | None:
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
        with self._connect() as connection:
            connection.execute(
                "UPDATE tryon_jobs SET saved = ?, expires_at = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND status = 'SUCCEEDED'",
                (int(saved), expires_at, datetime.now(UTC), job_id, user_id),
            )
        return self.get(job_id, user_id)

    def set_feedback(self, job_id: str, user_id: str, feedback: str) -> TryOnJob | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tryon_jobs SET feedback = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (feedback, datetime.now(UTC), job_id, user_id),
            )
        return self.get(job_id, user_id)

    def delete(self, job_id: str, user_id: str) -> TryOnJob | None:
        job = self.get(job_id, user_id)
        if job is None:
            return None
        with self._connect() as connection:
            connection.execute("DELETE FROM tryon_jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
        return job

    def recover_pending(self) -> list[str]:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tryon_jobs SET status = 'QUEUED', updated_at = ? WHERE status = 'PROCESSING'",
                (datetime.now(UTC),),
            )
            rows = connection.execute(
                "SELECT id FROM tryon_jobs WHERE status = 'QUEUED' ORDER BY created_at ASC"
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def cleanup_expired(self) -> list[str]:
        now = datetime.now(UTC)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT output_path FROM tryon_jobs WHERE expires_at <= ?", (now,)
            ).fetchall()
            connection.execute("DELETE FROM tryon_jobs WHERE expires_at <= ?", (now,))
        return [str(row["output_path"]) for row in rows if row["output_path"]]


def _job_from_row(row: Any) -> TryOnJob:
    raw_profile = json.loads(row["body_profile_json"] or "{}")
    if not raw_profile:
        raw_profile = _legacy_profile().to_dict()
    return TryOnJob(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        product_id=str(row["product_id"]),
        category=str(row["category"]),
        body_profile=SyntheticBodyProfile.from_dict(raw_profile),
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        expires_at=str(row["expires_at"]),
        attempt_count=int(row["attempt_count"]),
        output_key=row["output_path"],
        failure_code=row["failure_code"],
        saved=bool(row["saved"]),
        feedback=row["feedback"],
    )


def _legacy_profile() -> SyntheticBodyProfile:
    return SyntheticBodyProfile(170, 60, 88, 72, 94)


class LocalMediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise TryOnError("结果地址无效。", code="INVALID_RESULT_KEY")
        return path

    def put(self, key: str, content: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class LocalDispatcher:
    distributed = False

    async def enqueue(self, job_id: str) -> None:
        del job_id

    async def next(self, timeout_seconds: int = 5) -> str | None:
        del timeout_seconds
        return None

    async def ack(self, job_id: str) -> None:
        del job_id

    async def recover(self) -> None:
        return None


class HttpVirtualTryOnProvider:
    """Body-profile-conditioned synthetic-model virtual try-on provider."""

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
        body_profile: SyntheticBodyProfile,
        garment: PreparedImage,
        product_id: str,
        category: str,
        job_id: str,
    ) -> bytes:
        if not self.configured:
            raise ProviderUnavailable("当前环境尚未配置虚拟模特生成服务。")
        return await asyncio.to_thread(
            self._render_sync, body_profile, garment, product_id, category, job_id
        )

    def _render_sync(
        self,
        body_profile: SyntheticBodyProfile,
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
                "body_profile": json.dumps(body_profile.to_dict(), separators=(",", ":")),
                "prompt": _try_on_prompt(body_profile, category),
            },
            files={"garment_image": ("garment.jpg", garment.mime_type, garment.content)},
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
                "虚拟模特生成失败。",
                code="PROVIDER_REJECTED" if not retryable else "PROVIDER_UNAVAILABLE",
                retryable=retryable,
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ProviderUnavailable() from error
        if len(payload) > _MAX_PROVIDER_OUTPUT_BYTES:
            raise TryOnError("生成结果过大。", code="INVALID_PROVIDER_RESPONSE")
        if content_type.startswith("image/"):
            return payload
        if content_type == "application/json":
            return _image_from_provider_json(payload)
        raise TryOnError("模型服务返回了不支持的格式。", code="INVALID_PROVIDER_RESPONSE")


def _multipart_body(
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = "----fitme-" + uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ))
    for name, (filename, mime_type, content) in files.items():
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
        ))
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
            raise ValueError("missing image")
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error) as error:
        raise TryOnError("模型服务返回了无效图片。", code="INVALID_PROVIDER_RESPONSE") from error
    if len(image) > _MAX_PROVIDER_OUTPUT_BYTES:
        raise TryOnError("生成结果过大。", code="INVALID_PROVIDER_RESPONSE")
    return image


def _try_on_prompt(profile: SyntheticBodyProfile, category: str) -> str:
    measurements = (
        f"height {profile.height_cm:g} cm, weight {profile.weight_kg:g} kg, "
        f"chest {profile.chest_cm:g} cm, waist {profile.waist_cm:g} cm, hip {profile.hip_cm:g} cm"
    )
    optional = []
    if profile.shoulder_cm is not None:
        optional.append(f"shoulder {profile.shoulder_cm:g} cm")
    if profile.inseam_cm is not None:
        optional.append(f"inseam {profile.inseam_cm:g} cm")
    if optional:
        measurements += ", " + ", ".join(optional)
    return (
        "Create a photorealistic, fully synthetic adult virtual model. Do not depict a real or "
        "identifiable person. Use a neutral studio background and a natural full-body front pose. "
        f"Body measurements: {measurements}. Presentation: {profile.presentation.lower()}; "
        f"body shape: {profile.body_shape.lower()}; skin tone: {profile.skin_tone.lower()}. "
        f"Dress the model in garment_image as {category}, with a {profile.fit_preference.lower()} fit. "
        "Preserve garment color, pattern, logo, seams and silhouette. Render physically plausible "
        "drape, folds, occlusion and shadows. Do not add text, logos or watermarks."
    )


def prepare_garment_image(content: bytes) -> PreparedImage:
    return _normalize_image(content, max_long_edge=2048)


def prepare_provider_result(content: bytes) -> PreparedImage:
    return _normalize_image(content, max_long_edge=2048, max_bytes=_MAX_PROVIDER_OUTPUT_BYTES)


def _normalize_image(content: bytes, *, max_long_edge: int, max_bytes: int = _MAX_PROVIDER_OUTPUT_BYTES) -> PreparedImage:
    if not content:
        raise TryOnError("图片不能为空。", code="INVALID_IMAGE")
    if len(content) > max_bytes:
        raise TryOnError("图片文件过大。", code="IMAGE_TOO_LARGE")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            if source.width * source.height > _MAX_IMAGE_PIXELS:
                raise TryOnError("图片尺寸过大。", code="IMAGE_TOO_LARGE")
            normalized = ImageOps.exif_transpose(source).convert("RGB")
    except TryOnError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise TryOnError("图片格式无效。", code="INVALID_IMAGE") from error
    normalized.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    normalized.save(output, format="JPEG", quality=94, optimize=True)
    return PreparedImage(output.getvalue(), normalized.width, normalized.height)


def infer_category(product: dict[str, object]) -> str:
    source = " ".join(
        str(product.get(field) or "").casefold()
        for field in ("product_type_name", "product_group_name", "garment_group_name", "prod_name")
    )
    categories = (
        ("shoes", ("shoe", "sneaker", "boot", "sandal", "heel", "鞋", "靴")),
        ("dress", ("dress", "连衣裙", "礼服")),
        ("skirt", ("skirt", "半身裙")),
        ("bottom", ("trouser", "pants", "jean", "short", "legging", "裤", "牛仔")),
        ("outerwear", ("jacket", "coat", "blazer", "cardigan", "vest", "外套", "夹克", "风衣", "开衫")),
        ("top", ("shirt", "tee", "t-shirt", "blouse", "sweater", "hoodie", "top", "polo", "衬衫", "上衣", "卫衣", "针织")),
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
        raise TryOnError("Idempotency-Key 必须是 8-128 位安全字符。", code="INVALID_IDEMPOTENCY_KEY")
    return key


class VirtualTryOnService:
    def __init__(
        self,
        settings: VirtualTryOnSettings,
        *,
        store: JobStore | None = None,
        media_store: MediaStore | None = None,
        dispatcher: JobDispatcher | None = None,
        provider: HttpVirtualTryOnProvider | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or PostgresTryOnStore(settings)
        self.media_store = media_store or LocalMediaStore(settings.media_dir / "results")
        self.dispatcher = dispatcher or LocalDispatcher()
        self.provider = provider or HttpVirtualTryOnProvider(settings)
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
        body_profile: SyntheticBodyProfile,
        idempotency_key: str | None,
    ) -> tuple[TryOnJob, bool]:
        self.cleanup_if_due()
        job, created = self.store.create(
            user_id=user_id,
            product_id=str(product["article_id"]),
            category=infer_category(product),
            body_profile=body_profile,
            idempotency_key=idempotency_key,
            rate_limit_count=self.settings.rate_limit_count,
            rate_limit_window_seconds=self.settings.rate_limit_window_seconds,
            ttl_hours=self.settings.result_ttl_hours,
        )
        if created:
            submitted_counter.add(1, {"category": job.category})
        return job, created

    async def dispatch(self, job_id: str) -> None:
        if self.dispatcher.distributed:
            await self.dispatcher.enqueue(job_id)
            return
        with self._scheduled_lock:
            if job_id in self._scheduled:
                return
            self._scheduled.add(job_id)
        asyncio.create_task(self.process(job_id), name=f"try-on-{job_id}")

    async def recover(self) -> None:
        pending = self.store.recover_pending()
        await self.dispatcher.recover()
        for job_id in pending:
            await self.dispatch(job_id)

    async def process(self, job_id: str) -> None:
        try:
            async with self._semaphore:
                job = self.store.claim(job_id)
                if job is None:
                    return
                queue_latency.record(max(time.time() - _parse_timestamp(job.created_at).timestamp(), 0))
                try:
                    product = await asyncio.to_thread(load_catalog_product, job.product_id)
                    started = time.monotonic()
                    output = await self.provider.render(
                        body_profile=job.body_profile,
                        garment=load_product_image(product),
                        product_id=job.product_id,
                        category=job.category,
                        job_id=job.id,
                    )
                    provider_latency.record(time.monotonic() - started, {"category": job.category})
                    result = prepare_provider_result(output)
                    output_key = f"results/{job.user_id}/{job.id}.jpg"
                    await asyncio.to_thread(self.media_store.put, output_key, result.content)
                    self.store.succeed(job.id, output_key)
                    completed_counter.add(1, {"status": "succeeded", "category": job.category})
                    logger.info("try_on_succeeded job_id=%s category=%s attempt=%s", job.id, job.category, job.attempt_count)
                except TryOnError as error:
                    if error.retryable and job.attempt_count < 3:
                        self.store.retry(job.id)
                        await asyncio.sleep(0.5 * job.attempt_count)
                        if not self.dispatcher.distributed:
                            with self._scheduled_lock:
                                self._scheduled.discard(job.id)
                        await self.dispatch(job.id)
                    else:
                        self._fail_job(job, error.code)
                except Exception:
                    logger.exception("try_on_failed job_id=%s", job.id)
                    self._fail_job(job, "INTERNAL_ERROR")
        finally:
            with self._scheduled_lock:
                self._scheduled.discard(job_id)

    async def worker_loop(self) -> None:
        if not self.dispatcher.distributed:
            raise RuntimeError("VTO_REDIS_URL is required for the distributed worker")
        await self.recover()
        while True:
            job_id = await self.dispatcher.next()
            if not job_id:
                continue
            try:
                await self.process(job_id)
            finally:
                await self.dispatcher.ack(job_id)

    def _fail_job(self, job: TryOnJob, code: str) -> None:
        self.store.fail(job.id, code)
        completed_counter.add(1, {"status": "failed", "category": job.category, "code": code})
        logger.warning("try_on_failed job_id=%s code=%s", job.id, code)

    def cleanup_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        for key in self.store.cleanup_expired():
            self.media_store.delete(key)

    def delete(self, job_id: str, user_id: str) -> bool:
        job = self.store.delete(job_id, user_id)
        if job is None:
            return False
        if job.output_key:
            self.media_store.delete(job.output_key)
        return True

    def sign_result_url(self, job: TryOnJob) -> str | None:
        if job.status != "SUCCEEDED" or not job.output_key or not self.settings.result_signing_secret:
            return None
        expires_at = int(time.time()) + 15 * 60
        signature = self._signature(job, expires_at)
        return f"/api/try-on/jobs/{job.id}/result?expires={expires_at}&signature={signature}"

    def verify_result_signature(self, job: TryOnJob, expires: int, signature: str) -> bool:
        if expires < int(time.time()) or expires > int(time.time()) + 16 * 60:
            return False
        return hmac.compare_digest(signature, self._signature(job, expires))

    def _signature(self, job: TryOnJob, expires: int) -> str:
        message = f"{job.id}:{job.user_id}:{expires}".encode()
        return hmac.new(
            self.settings.result_signing_secret.encode(), message, hashlib.sha256
        ).hexdigest()


def build_virtual_try_on_service(settings: VirtualTryOnSettings | None = None) -> VirtualTryOnService:
    resolved = settings or VirtualTryOnSettings.from_env()
    store: JobStore | None = None
    media_store: MediaStore | None = None
    dispatcher: JobDispatcher | None = None
    if resolved.redis_url:
        from app.core.try_on_runtime import RedisJobDispatcher, RedisTryOnStore

        store = RedisTryOnStore(resolved)
        dispatcher = RedisJobDispatcher(resolved)
    elif resolved.database_url:
        store = PostgresTryOnStore(resolved)
    if resolved.s3_bucket:
        from app.core.try_on_runtime import S3MediaStore

        media_store = S3MediaStore(resolved)
    if store is None:
        raise RuntimeError(
            "VTO_REDIS_URL or VTO_DATABASE_URL is required for the try-on job store."
        )
    return VirtualTryOnService(
        resolved,
        store=store,
        media_store=media_store,
        dispatcher=dispatcher,
    )


def load_product_image(product: dict[str, object]) -> PreparedImage:
    image_path = str(product.get("image_path") or "").replace("\\", "/")
    if not image_path:
        raise TryOnError("该商品没有可用的试穿图片。", code="PRODUCT_IMAGE_UNAVAILABLE")
    from app.core.catalog_paths import get_catalog_image_dir

    image_root = get_catalog_image_dir().resolve()
    relative = Path(image_path)
    if relative.parts and relative.parts[0] == "images":
        relative = Path(*relative.parts[1:])
    candidate = (image_root / relative).resolve()
    if image_root not in candidate.parents or not candidate.is_file():
        raise TryOnError("该商品没有可用的试穿图片。", code="PRODUCT_IMAGE_UNAVAILABLE")
    try:
        return prepare_garment_image(candidate.read_bytes())
    except OSError as error:
        raise TryOnError("该商品没有可用的试穿图片。", code="PRODUCT_IMAGE_UNAVAILABLE") from error


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
    except (RuntimeError, PgError) as error:
        raise TryOnError("商品目录暂时不可用。", code="CATALOG_UNAVAILABLE", retryable=True) from error
    if row is None:
        raise TryOnError("未找到该商品。", code="PRODUCT_NOT_FOUND")
    return dict(row)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
