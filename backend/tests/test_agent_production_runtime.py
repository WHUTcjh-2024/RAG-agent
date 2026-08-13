from __future__ import annotations

# ruff: noqa: E402

import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException
from app.core.agent.memory import AgentMemoryStore
from app.core.agent.runtime import RedisTaskLock, create_task_lock


class FakeRedisLock:
    def __init__(self, *, acquire: bool = True, extend: bool = True) -> None:
        self.acquire_result = acquire
        self.extend_result = extend
        self.released = False

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is True
        return self.acquire_result

    def extend(self, _ttl: int, *, replace_ttl: bool) -> bool:
        assert replace_ttl is True
        return self.extend_result

    def release(self) -> None:
        self.released = True


class FakeRedis:
    def __init__(self, lock: FakeRedisLock) -> None:
        self.value = lock
        self.calls: list[tuple[str, int, int, bool]] = []

    def lock(
        self,
        key: str,
        *,
        timeout: int,
        blocking_timeout: int,
        thread_local: bool,
    ) -> FakeRedisLock:
        self.calls.append((key, timeout, blocking_timeout, thread_local))
        return self.value


def test_redis_lease_returns_retryable_conflict_without_executing() -> None:
    fake_lock = FakeRedisLock(acquire=False)
    lease = RedisTaskLock(
        FakeRedis(fake_lock), ttl_seconds=15, acquire_timeout_seconds=0
    )

    with pytest.raises(AgentException) as error:
        with lease.hold("same-task"):
            raise AssertionError("must not enter a contended task")

    assert error.value.code == ErrorCode.TASK_IN_PROGRESS
    assert error.value.retryable is True
    assert error.value.status_code == 409


def test_redis_lease_has_an_ownership_release_path() -> None:
    fake_lock = FakeRedisLock()
    fake_redis = FakeRedis(fake_lock)
    lease = RedisTaskLock(fake_redis, ttl_seconds=15, acquire_timeout_seconds=0)

    with lease.hold("task-1"):
        pass

    assert fake_redis.calls == [("atelier:agent:task-lock:task-1", 15, 0, False)]
    assert fake_lock.released is True


def test_redis_runtime_configuration_fails_fast_without_a_connection(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_TASK_LOCK_BACKEND", "redis")
    monkeypatch.delenv("AGENT_REDIS_URL", raising=False)

    with pytest.raises(RuntimeError, match="AGENT_REDIS_URL"):
        create_task_lock()


def test_postgres_memory_configuration_fails_fast_without_a_database_url(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "postgres")
    monkeypatch.delenv("AGENT_MEMORY_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="AGENT_MEMORY_DATABASE_URL"):
        AgentMemoryStore()


def test_prometheus_metrics_do_not_use_task_or_user_labels() -> None:
    from app.core.agent.metrics import metrics

    metrics.record_span("agent.node.retrieve_candidates", 12, "ok")
    payload = metrics.render().decode("utf-8")

    assert "agent_node_total" in payload
    assert 'node="retrieve_candidates"' in payload
    assert "task_id" not in payload
    assert "user_id" not in payload
