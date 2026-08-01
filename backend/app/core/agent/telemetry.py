from __future__ import annotations

import logging
import os
import sys
from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Any, Iterator
from contextlib import contextmanager

try:  # Keep local development usable when optional observability packages are absent.
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
except ImportError:  # pragma: no cover - exercised only in an incomplete local install
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    duration_ms: float
    outcome: str
    attributes: dict[str, str | int | float | bool]


class AgentTelemetry:
    """Privacy-safe task spans, exportable through the configured OpenTelemetry provider.

    Event attributes deliberately contain identifiers and operational dimensions only;
    prompts, retrieval documents, image paths, and model output are never recorded.
    """

    def __init__(self, capacity: int = 300) -> None:
        self._events: deque[TelemetryEvent] = deque(maxlen=capacity)
        self._lock = Lock()
        if trace and TracerProvider and type(trace.get_tracer_provider()).__name__ == "ProxyTracerProvider":
            trace.set_tracer_provider(TracerProvider())
        self._tracer = trace.get_tracer("atelier.agent") if trace else None

    @contextmanager
    def span(self, name: str, **attributes: str | int | float | bool | None) -> Iterator[dict[str, str | int | float | bool]]:
        safe = {key: value for key, value in attributes.items() if value is not None}
        started = perf_counter()
        outcome = "ok"
        scope = self._tracer.start_as_current_span(name) if self._tracer else None
        span = scope.__enter__() if scope else None
        if span:
            for key, value in safe.items():
                span.set_attribute(key, value)
        try:
            yield safe
        except Exception as error:
            outcome = "error"
            safe["error.type"] = type(error).__name__
            if span:
                span.record_exception(error)
                span.set_attribute("agent.outcome", outcome)
            raise
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 3)
            safe["agent.duration_ms"] = duration_ms
            safe["agent.outcome"] = outcome
            if span:
                for key, value in safe.items():
                    span.set_attribute(key, value)
            if scope:
                scope.__exit__(*sys.exc_info())
            event = TelemetryEvent(name=name, duration_ms=duration_ms, outcome=outcome, attributes=dict(safe))
            with self._lock:
                self._events.append(event)
            logger.info("agent_telemetry name=%s duration_ms=%s outcome=%s", name, duration_ms, outcome)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)[-max(1, min(limit, 100)):]
        return [
            {
                "name": item.name,
                "duration_ms": item.duration_ms,
                "outcome": item.outcome,
                "attributes": item.attributes,
            }
            for item in events
        ]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
        failures = sum(event.outcome == "error" for event in events)
        return {"events": len(events), "failures": failures, "recent": self.recent()}


telemetry = AgentTelemetry(capacity=int(os.getenv("AGENT_TELEMETRY_CAPACITY", "300")))
