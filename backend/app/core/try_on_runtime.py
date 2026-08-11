from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import boto3
import redis
from botocore.exceptions import ClientError

from app.core.virtual_try_on import (
    SyntheticBodyProfile,
    TryOnError,
    TryOnJob,
    VirtualTryOnSettings,
)


class RedisTryOnStore:
    """Shared job state for horizontally scaled API and worker replicas."""

    def __init__(self, settings: VirtualTryOnSettings) -> None:
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.prefix = settings.redis_prefix

    def _job_key(self, job_id: str) -> str:
        return f"{self.prefix}:job:{job_id}"

    def _idempotency_key(self, user_id: str, value: str) -> str:
        digest = hashlib.sha256(f"{user_id}:{value}".encode()).hexdigest()
        return f"{self.prefix}:idempotency:{digest}"

    def _recent_key(self, user_id: str) -> str:
        return f"{self.prefix}:recent:{user_id}"

    @property
    def _active_key(self) -> str:
        return f"{self.prefix}:active"

    @property
    def _expiry_key(self) -> str:
        return f"{self.prefix}:expiry"

    def find_idempotent(self, user_id: str, idempotency_key: str) -> TryOnJob | None:
        job_id = self.client.get(self._idempotency_key(user_id, idempotency_key))
        return self.get(str(job_id), user_id) if job_id else None

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
        if idempotency_key:
            existing = self.find_idempotent(user_id, idempotency_key)
            if existing is not None:
                return existing, False

        now = datetime.now(UTC)
        job = TryOnJob(
            id=uuid4().hex,
            user_id=user_id,
            product_id=product_id,
            category=category,
            body_profile=body_profile,
            status="QUEUED",
            created_at=_timestamp(now),
            updated_at=_timestamp(now),
            expires_at=_timestamp(now + timedelta(hours=ttl_hours)),
            attempt_count=0,
            output_key=None,
            failure_code=None,
        )

        bucket = int(time.time()) // rate_limit_window_seconds
        rate_key = f"{self.prefix}:rate:{user_id}:{bucket}"
        idempotency_redis_key = (
            self._idempotency_key(user_id, idempotency_key) if idempotency_key else None
        )
        watched_keys = [rate_key]
        if idempotency_redis_key:
            watched_keys.append(idempotency_redis_key)

        for _ in range(10):
            with self.client.pipeline() as pipeline:
                try:
                    pipeline.watch(*watched_keys)
                    if idempotency_redis_key:
                        existing_id = pipeline.get(idempotency_redis_key)
                        if existing_id:
                            pipeline.unwatch()
                            existing = self.get(str(existing_id), user_id)
                            if existing is not None:
                                return existing, False
                            self._delete_stale_idempotency(idempotency_redis_key, str(existing_id))
                            continue

                    usage = int(pipeline.get(rate_key) or 0)
                    if usage >= rate_limit_count:
                        pipeline.unwatch()
                        raise TryOnError(
                            "试穿次数过多，请稍后再试。",
                            code="RATE_LIMITED",
                            retryable=True,
                        )

                    pipeline.multi()
                    pipeline.set(rate_key, usage + 1, ex=rate_limit_window_seconds + 5)
                    self._queue_save(pipeline, job)
                    if idempotency_redis_key:
                        pipeline.set(
                            idempotency_redis_key,
                            job.id,
                            ex=ttl_hours * 3600 + 3600,
                        )
                    pipeline.execute()
                    return job, True
                except redis.WatchError:
                    continue
        raise TryOnError("请求冲突，请重试。", code="STORE_CONFLICT", retryable=True)

    def get(self, job_id: str, user_id: str) -> TryOnJob | None:
        job = self.get_unscoped(job_id)
        return job if job and job.user_id == user_id else None

    def get_unscoped(self, job_id: str) -> TryOnJob | None:
        payload = self.client.get(self._job_key(job_id))
        return _job_from_json(payload) if payload else None

    def claim(self, job_id: str) -> TryOnJob | None:
        key = self._job_key(job_id)
        for _ in range(5):
            with self.client.pipeline() as pipeline:
                try:
                    pipeline.watch(key)
                    payload = pipeline.get(key)
                    if not payload:
                        pipeline.unwatch()
                        return None
                    job = _job_from_json(payload)
                    if job.status != "QUEUED":
                        pipeline.unwatch()
                        return None
                    claimed = replace(
                        job,
                        status="PROCESSING",
                        attempt_count=job.attempt_count + 1,
                        updated_at=_timestamp(datetime.now(UTC)),
                    )
                    pipeline.multi()
                    pipeline.set(key, _job_json(claimed), ex=_redis_ttl(claimed))
                    pipeline.execute()
                    return claimed
                except redis.WatchError:
                    continue
        return None

    def retry(self, job_id: str) -> None:
        self._mutate(job_id, lambda job: replace(job, status="QUEUED", updated_at=_timestamp(datetime.now(UTC))))

    def succeed(self, job_id: str, output_key: str) -> None:
        self._mutate(
            job_id,
            lambda job: replace(
                job,
                status="SUCCEEDED",
                output_key=output_key,
                failure_code=None,
                updated_at=_timestamp(datetime.now(UTC)),
            ),
        )
        self.client.zrem(self._active_key, job_id)

    def fail(self, job_id: str, failure_code: str) -> None:
        self._mutate(
            job_id,
            lambda job: replace(
                job,
                status="FAILED",
                failure_code=failure_code,
                updated_at=_timestamp(datetime.now(UTC)),
            ),
        )
        self.client.zrem(self._active_key, job_id)

    def _mutate(self, job_id: str, transform: Any) -> TryOnJob | None:
        key = self._job_key(job_id)
        for _ in range(5):
            with self.client.pipeline() as pipeline:
                try:
                    pipeline.watch(key)
                    payload = pipeline.get(key)
                    if not payload:
                        pipeline.unwatch()
                        return None
                    updated = transform(_job_from_json(payload))
                    pipeline.multi()
                    pipeline.set(key, _job_json(updated), ex=_redis_ttl(updated))
                    pipeline.zadd(self._expiry_key, {updated.id: _epoch(updated.expires_at)})
                    pipeline.execute()
                    return updated
                except redis.WatchError:
                    continue
        return None

    def _save(self, job: TryOnJob) -> None:
        with self.client.pipeline() as pipeline:
            self._queue_save(pipeline, job)
            pipeline.execute()

    def _queue_save(self, pipeline: Any, job: TryOnJob) -> None:
        ttl = _redis_ttl(job)
        pipeline.set(self._job_key(job.id), _job_json(job), ex=ttl)
        pipeline.zadd(self._recent_key(job.user_id), {job.id: _epoch(job.created_at)})
        pipeline.expire(self._recent_key(job.user_id), max(ttl, 3600))
        pipeline.zadd(self._active_key, {job.id: _epoch(job.created_at)})
        pipeline.zadd(self._expiry_key, {job.id: _epoch(job.expires_at)})

    def _delete_stale_idempotency(self, key: str, expected_job_id: str) -> None:
        self.client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            expected_job_id,
        )

    def list_user(self, user_id: str, limit: int) -> list[TryOnJob]:
        ids = self.client.zrevrange(self._recent_key(user_id), 0, max(limit * 2, limit) - 1)
        jobs = [self.get(str(job_id), user_id) for job_id in ids]
        now = datetime.now(UTC)
        return [job for job in jobs if job and _datetime(job.expires_at) > now][:limit]

    def set_saved(self, job_id: str, user_id: str, saved: bool, ttl_hours: int) -> TryOnJob | None:
        job = self.get(job_id, user_id)
        if job is None or job.status != "SUCCEEDED":
            return None
        return self._mutate(
            job_id,
            lambda current: replace(
                current,
                saved=saved,
                expires_at=_timestamp(datetime.now(UTC) + timedelta(hours=ttl_hours)),
                updated_at=_timestamp(datetime.now(UTC)),
            ),
        )

    def set_feedback(self, job_id: str, user_id: str, feedback: str) -> TryOnJob | None:
        if self.get(job_id, user_id) is None:
            return None
        return self._mutate(
            job_id,
            lambda current: replace(current, feedback=feedback, updated_at=_timestamp(datetime.now(UTC))),
        )

    def delete(self, job_id: str, user_id: str) -> TryOnJob | None:
        job = self.get(job_id, user_id)
        if job is None:
            return None
        with self.client.pipeline() as pipeline:
            pipeline.delete(self._job_key(job_id))
            pipeline.zrem(self._recent_key(user_id), job_id)
            pipeline.zrem(self._active_key, job_id)
            pipeline.zrem(self._expiry_key, job_id)
            pipeline.execute()
        return job

    def recover_pending(self) -> list[str]:
        ids = self.client.zrange(self._active_key, 0, -1)
        pending: list[str] = []
        for job_id in ids:
            job = self.get_unscoped(str(job_id))
            if job is None:
                self.client.zrem(self._active_key, job_id)
                continue
            if job.status == "PROCESSING":
                self.retry(job.id)
            if job.status in {"QUEUED", "PROCESSING"}:
                pending.append(job.id)
        return pending

    def cleanup_expired(self) -> list[str]:
        ids = self.client.zrangebyscore(self._expiry_key, 0, time.time())
        output_keys: list[str] = []
        for job_id in ids:
            job = self.get_unscoped(str(job_id))
            if job and job.output_key:
                output_keys.append(job.output_key)
            if job:
                self.delete(job.id, job.user_id)
            else:
                self.client.zrem(self._expiry_key, job_id)
        return output_keys


class RedisJobDispatcher:
    """At-least-once Redis queue with a recoverable processing list."""

    distributed = True

    def __init__(self, settings: VirtualTryOnSettings) -> None:
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue = f"{settings.redis_prefix}:queue"
        self.processing = f"{settings.redis_prefix}:processing"

    async def enqueue(self, job_id: str) -> None:
        await asyncio.to_thread(self.client.lpush, self.queue, job_id)

    async def next(self, timeout_seconds: int = 5) -> str | None:
        value = await asyncio.to_thread(
            self.client.brpoplpush, self.queue, self.processing, timeout_seconds
        )
        return str(value) if value else None

    async def ack(self, job_id: str) -> None:
        await asyncio.to_thread(self.client.lrem, self.processing, 1, job_id)

    async def recover(self) -> None:
        while True:
            value = await asyncio.to_thread(self.client.rpoplpush, self.processing, self.queue)
            if value is None:
                return


class S3MediaStore:
    """Private S3-compatible result storage; MinIO is used by docker-compose."""

    def __init__(self, settings: VirtualTryOnSettings) -> None:
        kwargs: dict[str, object] = {
            "service_name": "s3",
            "region_name": settings.s3_region,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_access_key:
            kwargs["aws_access_key_id"] = settings.s3_access_key
        if settings.s3_secret_key:
            kwargs["aws_secret_access_key"] = settings.s3_secret_key
        self.client = boto3.client(**kwargs)
        self.bucket = settings.s3_bucket

    def put(self, key: str, content: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType="image/jpeg",
            CacheControl="private, no-store",
            Metadata={"synthetic": "true"},
        )

    def read(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def _job_json(job: TryOnJob) -> str:
    payload = asdict(job)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _job_from_json(payload: str) -> TryOnJob:
    value = json.loads(payload)
    value["body_profile"] = SyntheticBodyProfile.from_dict(value["body_profile"])
    return TryOnJob(**value)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _epoch(value: str) -> float:
    return _datetime(value).timestamp()


def _redis_ttl(job: TryOnJob) -> int:
    return max(int(_epoch(job.expires_at) - time.time()) + 3600, 3600)
