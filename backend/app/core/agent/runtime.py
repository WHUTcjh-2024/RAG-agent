from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from threading import Event, Lock, RLock, Thread
from time import monotonic
from typing import ContextManager, Iterator, Protocol

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException
from app.core.agent.metrics import metrics


logger = logging.getLogger(__name__)


class TaskLock(Protocol):
    """Mutual exclusion for one idempotent workflow task across replicas."""

    def hold(self, task_id: str) -> ContextManager[None]: ...


class LocalTaskLockPool:
    """Development-only lock implementation for a single Python process."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._entries: dict[str, tuple[RLock, int]] = {}

    @contextmanager
    def hold(self, task_id: str) -> Iterator[None]:
        with self._guard:
            lock, references = self._entries.get(task_id, (RLock(), 0))
            self._entries[task_id] = (lock, references + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._guard:
                current_lock, current_references = self._entries[task_id]
                if current_references == 1:
                    del self._entries[task_id]
                else:
                    self._entries[task_id] = (
                        current_lock,
                        current_references - 1,
                    )


class RedisTaskLock:
    """Ownership-checked Redis lease with bounded acquisition and renewal.

    The lease prevents duplicate *execution*, while Postgres task/checkpoint
    uniqueness remains the source of truth for idempotency. A lease expiry can
    therefore never turn into a duplicate business write by itself.
    """

    def __init__(
        self,
        client,
        *,
        prefix: str = "atelier:agent:task-lock",
        ttl_seconds: int = 90,
        acquire_timeout_seconds: int = 3,
    ) -> None:
        if ttl_seconds < 15:
            raise ValueError("AGENT_TASK_LOCK_TTL_SECONDS must be at least 15.")
        if acquire_timeout_seconds < 0:
            raise ValueError(
                "AGENT_TASK_LOCK_ACQUIRE_TIMEOUT_SECONDS must be non-negative."
            )
        self.client = client
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = ttl_seconds
        self.acquire_timeout_seconds = acquire_timeout_seconds

    def _key(self, task_id: str) -> str:
        return f"{self.prefix}:{task_id}"

    @contextmanager
    def hold(self, task_id: str) -> Iterator[None]:
        key = self._key(task_id)
        # redis-py verifies token ownership on release/extend. thread_local=False
        # lets the renewal thread share this lock safely.
        lock = self.client.lock(
            key,
            timeout=self.ttl_seconds,
            blocking_timeout=self.acquire_timeout_seconds,
            thread_local=False,
        )
        started = monotonic()
        acquired = lock.acquire(blocking=True)
        wait_seconds = monotonic() - started
        if not acquired:
            metrics.record_lock_contended()
            raise AgentException(
                ErrorCode.TASK_IN_PROGRESS,
                "The same agent task is already executing. Retry with the same task ID.",
                status_code=409,
                retryable=True,
                stage="acquire_task_lease",
                details={"retry_after_seconds": max(1, self.ttl_seconds // 3)},
            )
        metrics.record_lock_acquired(wait_seconds)

        stop = Event()
        lease_lost = Event()
        renewer = Thread(
            target=self._renew,
            args=(lock, stop, lease_lost, task_id),
            name=f"agent-lock-renew:{task_id[:16]}",
            daemon=True,
        )
        renewer.start()
        try:
            yield
            if lease_lost.is_set():
                # Do not claim success if Redis could no longer prove ownership.
                # The durable checkpoint/idempotency records make retry safe.
                raise AgentException(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Task lease was lost during execution; retry with the same task ID.",
                    status_code=503,
                    retryable=True,
                    stage="renew_task_lease",
                )
        finally:
            stop.set()
            renewer.join(timeout=1)
            try:
                lock.release()
            except Exception as error:  # Lease may already be expired/lost.
                logger.warning(
                    "agent_task_lease_release_failed task_id=%s error_type=%s",
                    task_id,
                    type(error).__name__,
                )

    def _renew(self, lock, stop: Event, lease_lost: Event, task_id: str) -> None:
        interval = max(5, self.ttl_seconds // 3)
        while not stop.wait(interval):
            try:
                if not lock.extend(self.ttl_seconds, replace_ttl=True):
                    lease_lost.set()
                    metrics.record_lock_lost()
                    logger.error("agent_task_lease_lost task_id=%s", task_id)
                    return
            except Exception as error:
                lease_lost.set()
                metrics.record_lock_lost()
                logger.error(
                    "agent_task_lease_renew_failed task_id=%s error_type=%s",
                    task_id,
                    type(error).__name__,
                )
                return


def create_task_lock() -> TaskLock:
    """Select an execution lock deliberately; production never falls back silently."""

    backend = os.getenv("AGENT_TASK_LOCK_BACKEND", "local").strip().casefold()
    if backend == "local":
        return LocalTaskLockPool()
    if backend != "redis":
        raise RuntimeError("AGENT_TASK_LOCK_BACKEND must be 'local' or 'redis'.")

    redis_url = os.getenv("AGENT_REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError(
            "AGENT_REDIS_URL is required when AGENT_TASK_LOCK_BACKEND=redis."
        )
    try:
        import redis
    except ImportError as error:  # pragma: no cover - deployment dependency guard
        raise RuntimeError(
            "redis package is required for Redis task leases."
        ) from error

    ttl_seconds = _positive_int("AGENT_TASK_LOCK_TTL_SECONDS", 90, minimum=15)
    acquire_timeout_seconds = _positive_int(
        "AGENT_TASK_LOCK_ACQUIRE_TIMEOUT_SECONDS", 3, minimum=0
    )
    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    # Fail fast at startup instead of accidentally serving a process-local agent.
    client.ping()
    return RedisTaskLock(
        client,
        prefix=os.getenv("AGENT_TASK_LOCK_PREFIX", "atelier:agent:task-lock"),
        ttl_seconds=ttl_seconds,
        acquire_timeout_seconds=acquire_timeout_seconds,
    )


def _positive_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}.")
    return value
