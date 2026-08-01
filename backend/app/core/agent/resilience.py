from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CircuitBreakerSnapshot:
    state: str
    consecutive_failures: int


class CircuitBreaker:
    """Small process-local breaker for read-only upstream dependencies."""

    def __init__(self, name: str, *, failure_threshold: int = 3, recovery_seconds: float = 30) -> None:
        if failure_threshold < 1 or recovery_seconds <= 0:
            raise ValueError("Circuit breaker threshold and recovery window must be positive.")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    def _allow(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            if monotonic() - self._opened_at >= self.recovery_seconds:
                self._opened_at = None
                self._consecutive_failures = 0
                return
        from app.core.agent.contracts import ErrorCode
        from app.core.agent.errors import AgentException

        raise AgentException(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"{self.name} is temporarily unavailable; please retry shortly.",
            status_code=503,
            retryable=True,
            stage=self.name,
        )

    def call(self, operation: Callable[[], T]) -> T:
        self._allow()
        try:
            result = operation()
        except Exception:
            with self._lock:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    self._opened_at = monotonic()
            raise
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None
        return result

    def snapshot(self) -> CircuitBreakerSnapshot:
        with self._lock:
            return CircuitBreakerSnapshot(
                state="open" if self._opened_at is not None else "closed",
                consecutive_failures=self._consecutive_failures,
            )
