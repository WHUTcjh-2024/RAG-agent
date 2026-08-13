from __future__ import annotations

try:  # Metrics are optional in local unit-test environments.
    from prometheus_client import (  # type: ignore[import-not-found]
        CONTENT_TYPE_LATEST,
        Counter,
        Histogram,
        generate_latest,
    )
except ImportError:  # pragma: no cover - deployment dependency guard
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"
    Counter = Histogram = None  # type: ignore[assignment,misc]
    generate_latest = None  # type: ignore[assignment]


class AgentMetrics:
    """Low-cardinality SLI metrics; no prompt, user ID, or task ID labels."""

    def __init__(self) -> None:
        self._task_total = (
            Counter("agent_task_total", "Completed agent tasks", ["outcome"])
            if Counter
            else None
        )
        self._task_duration = (
            Histogram("agent_task_duration_seconds", "Agent task latency")
            if Histogram
            else None
        )
        self._node_total = (
            Counter("agent_node_total", "Agent workflow nodes", ["node", "outcome"])
            if Counter
            else None
        )
        self._node_duration = (
            Histogram(
                "agent_node_duration_seconds",
                "Agent workflow-node latency",
                ["node", "outcome"],
            )
            if Histogram
            else None
        )
        self._lock_acquired = (
            Counter("agent_task_lease_acquired_total", "Acquired task leases")
            if Counter
            else None
        )
        self._lock_contended = (
            Counter(
                "agent_task_lease_contended_total", "Task lease acquisition conflicts"
            )
            if Counter
            else None
        )
        self._lock_lost = (
            Counter("agent_task_lease_lost_total", "Task leases lost during execution")
            if Counter
            else None
        )
        self._lock_wait = (
            Histogram("agent_task_lease_wait_seconds", "Task lease acquisition time")
            if Histogram
            else None
        )

    def record_span(self, name: str, duration_ms: float, outcome: str) -> None:
        duration_seconds = duration_ms / 1000
        if name == "agent.task":
            if self._task_total:
                self._task_total.labels(outcome=outcome).inc()
            if self._task_duration:
                self._task_duration.observe(duration_seconds)
        elif name.startswith("agent.node."):
            node = name.removeprefix("agent.node.")
            if self._node_total:
                self._node_total.labels(node=node, outcome=outcome).inc()
            if self._node_duration:
                self._node_duration.labels(node=node, outcome=outcome).observe(
                    duration_seconds
                )

    def record_lock_acquired(self, wait_seconds: float) -> None:
        if self._lock_acquired:
            self._lock_acquired.inc()
        if self._lock_wait:
            self._lock_wait.observe(wait_seconds)

    def record_lock_contended(self) -> None:
        if self._lock_contended:
            self._lock_contended.inc()

    def record_lock_lost(self) -> None:
        if self._lock_lost:
            self._lock_lost.inc()

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST

    def render(self) -> bytes:
        return (
            generate_latest()
            if generate_latest
            else b"# prometheus-client is unavailable\n"
        )


metrics = AgentMetrics()
