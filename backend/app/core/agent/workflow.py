from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.core.agent.contracts import AgentResponse, ErrorCode, NodeTrace
from app.core.agent.errors import AgentException, invalid_input
from app.core.agent.memory import validate_session_id
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.workflow_nodes import ShoppingAgentWorkflowNodes
from app.core.agent.workflow_state import (
    AgentState,
    validate_task_id,
    workflow_enabled as workflow_enabled,
)
from app.core.agent.runtime import TaskLock, create_task_lock
from app.core.request_id import normalize_request_id
from app.core.agent.telemetry import telemetry


DEFAULT_CHECKPOINT_DB = (
    Path(__file__).resolve().parents[3] / "data" / "sqlite" / "agent_checkpoints.db"
)
DEFAULT_CHECKPOINT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_REACT_MAX_STEPS = 3


def _checkpoint_ttl_seconds() -> int:
    configured = os.getenv("CHECKPOINT_TTL_SECONDS", str(DEFAULT_CHECKPOINT_TTL_SECONDS))
    try:
        seconds = int(configured)
    except ValueError as error:
        raise RuntimeError("CHECKPOINT_TTL_SECONDS must be a positive integer.") from error
    if seconds <= 0:
        raise RuntimeError("CHECKPOINT_TTL_SECONDS must be a positive integer.")
    return seconds


def _react_max_steps() -> int:
    configured = os.getenv("AGENT_REACT_MAX_STEPS", str(DEFAULT_REACT_MAX_STEPS))
    try:
        steps = int(configured)
    except ValueError as error:
        raise RuntimeError("AGENT_REACT_MAX_STEPS must be between 1 and 6.") from error
    if not 1 <= steps <= 6:
        raise RuntimeError("AGENT_REACT_MAX_STEPS must be between 1 and 6.")
    return steps


class RecoverableShoppingAgentWorkflow:
    NODE_ORDER = (
        "validate_input",
        "understand_request",
        "load_context",
        "plan_tools",
        "retrieve_candidates",
        "observe_and_replan",
        "verify_constraints",
        "build_evidence",
        "generate_answer",
        "wait_for_confirmation",
        "complete",
    )

    def __init__(
        self,
        orchestrator: ShoppingAgentOrchestrator,
        checkpoint_path: str | Path | None = None,
        task_lock: TaskLock | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.checkpoint_ttl_seconds = _checkpoint_ttl_seconds()
        self.react_max_steps = _react_max_steps()
        self._storage_backend = os.getenv("AGENT_CHECKPOINT_BACKEND", "sqlite").strip().casefold()
        self._connection: sqlite3.Connection | None = None
        self._checkpointer_context = None
        self.checkpoint_path: Path | None = None
        self._checkpointer = self._create_checkpointer(checkpoint_path)
        self._locks = task_lock or create_task_lock()
        self.nodes = ShoppingAgentWorkflowNodes(orchestrator)
        self.graph = self._build_graph()

    def close(self) -> None:
        if self._checkpointer_context is not None:
            self._checkpointer_context.__exit__(None, None, None)
            self._checkpointer_context = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _create_checkpointer(self, checkpoint_path: str | Path | None):
        if self._storage_backend == "sqlite":
            configured = os.getenv("AGENT_CHECKPOINT_DB_PATH", "").strip()
            self.checkpoint_path = Path(
                checkpoint_path or configured or DEFAULT_CHECKPOINT_DB
            ).resolve()
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                self.checkpoint_path,
                timeout=30,
                check_same_thread=False,
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_checkpoint_ttls (
                    task_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._cleanup_expired_checkpoints()
            saver = SqliteSaver(self._connection)
            saver.setup()
            return saver
        if self._storage_backend != "postgres":
            raise RuntimeError("AGENT_CHECKPOINT_BACKEND must be 'sqlite' or 'postgres'.")
        if checkpoint_path is not None:
            raise ValueError("checkpoint_path is only supported by the SQLite checkpointer.")
        database_url = os.getenv("AGENT_CHECKPOINT_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError(
                "AGENT_CHECKPOINT_DATABASE_URL is required when AGENT_CHECKPOINT_BACKEND=postgres."
            )
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as error:  # pragma: no cover - production dependency guard
            raise RuntimeError(
                "Install langgraph-checkpoint-postgres and psycopg for the Postgres checkpointer."
            ) from error
        self._checkpointer_context = PostgresSaver.from_conn_string(database_url)
        saver = self._checkpointer_context.__enter__()
        if os.getenv("AGENT_CHECKPOINT_AUTO_SETUP", "false").strip().casefold() in {"1", "true", "yes"}:
            saver.setup()
        return saver

    def _cleanup_expired_checkpoints(self) -> int:
        if self._connection is None:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.checkpoint_ttl_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        expired = self._connection.execute(
            "SELECT task_id FROM agent_checkpoint_ttls WHERE updated_at < ?", (cutoff,)
        ).fetchall()
        for (task_id,) in expired:
            self._delete_task_checkpoints(str(task_id))
        return len(expired)

    def _register_checkpoint_task(self, task_id: str) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            """
            INSERT INTO agent_checkpoint_ttls(task_id) VALUES (?)
            ON CONFLICT(task_id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP
            """,
            (task_id,),
        )

    def _delete_task_checkpoints(self, task_id: str) -> None:
        if self._connection is not None:
            self._connection.execute("DELETE FROM checkpoints WHERE thread_id=?", (task_id,))
            self._connection.execute("DELETE FROM writes WHERE thread_id=?", (task_id,))
            self._connection.execute("DELETE FROM agent_checkpoint_ttls WHERE task_id=?", (task_id,))
            return
        delete_thread = getattr(self._checkpointer, "delete_thread", None)
        if delete_thread is None:
            raise RuntimeError("Configured checkpointer does not support thread deletion.")
        delete_thread(task_id)

    def purge_tasks(self, task_ids: list[str]) -> None:
        with self._locks.hold("checkpoint-cleanup"):
            for task_id in task_ids:
                self._delete_task_checkpoints(validate_task_id(task_id))

    def prune_expired_checkpoints(self) -> int:
        """Run from one scheduled maintenance job, not every API replica."""
        return self._cleanup_expired_checkpoints()

    @staticmethod
    def _fingerprint(
        message: str,
        session_id: str,
        language: str,
        has_image: bool,
        decision_product_id: str | None,
        trusted_user_id: str | None,
    ) -> str:
        raw = "\x1f".join(
            (
                message.strip(),
                session_id,
                language,
                "image" if has_image else "text",
                decision_product_id or "",
                trusted_user_id or "",
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _append(values: list[Any] | None, item: Any) -> list[Any]:
        return [*(values or []), item]

    def _instrument(self, node: str, function):
        def wrapped(state: AgentState) -> AgentState:
            writer = get_stream_writer()
            writer({"node": node, "state": "started"})
            started = perf_counter()
            try:
                if self.orchestrator.memory.task_cancelled(state["task_id"]):
                    raise AgentException(
                        ErrorCode.TASK_CANCELLED,
                        "Task was cancelled.",
                        status_code=409,
                        stage=node,
                    )
                with telemetry.span(
                    f"agent.node.{node}",
                    **{
                        "agent.task_id": state["task_id"],
                        "agent.request_id": state["request_id"],
                        "agent.node": node,
                    },
                ):
                    updates: AgentState = function(state)
            except Exception as error:
                duration_ms = round((perf_counter() - started) * 1000, 3)
                writer(
                    {
                        "node": node,
                        "state": "failed",
                        "duration_ms": duration_ms,
                        "summary": type(error).__name__,
                    }
                )
                raise

            duration_ms = round((perf_counter() - started) * 1000, 3)
            summary = self.nodes.summary(node, updates)
            trace = NodeTrace(
                node=node,
                state="completed",
                duration_ms=duration_ms,
                summary=summary,
            ).model_dump(mode="json")
            node_traces = self._append(state.get("node_trace"), trace)
            updates["executed_nodes"] = self._append(state.get("executed_nodes"), node)
            updates["node_trace"] = node_traces
            if "response" in updates:
                updates["response"]["node_trace"] = node_traces
            writer(
                {
                    "node": node,
                    "state": "completed",
                    "duration_ms": duration_ms,
                    "summary": summary,
                }
            )
            return updates

        return wrapped

    @staticmethod
    def _retryable(error: Exception) -> bool:
        return isinstance(error, (RuntimeError, TimeoutError)) or (
            isinstance(error, AgentException) and error.retryable
        )

    def _build_graph(self):
        builder = StateGraph(AgentState)
        for name, function in self.nodes.mapping.items():
            retry_policy = None
            if name == "retrieve_candidates":
                retry_policy = RetryPolicy(
                    initial_interval=0,
                    backoff_factor=1,
                    max_interval=0,
                    max_attempts=3,
                    jitter=False,
                    retry_on=self._retryable,
                )
            builder.add_node(
                name,
                self._instrument(name, function),
                retry_policy=retry_policy,
            )

        builder.add_edge(START, "validate_input")
        for source, target in (
            ("validate_input", "understand_request"),
            ("understand_request", "load_context"),
            ("load_context", "plan_tools"),
            ("plan_tools", "retrieve_candidates"),
            ("verify_constraints", "build_evidence"),
            ("build_evidence", "generate_answer"),
        ):
            builder.add_edge(source, target)
        builder.add_edge("retrieve_candidates", "observe_and_replan")
        builder.add_conditional_edges(
            "observe_and_replan",
            self.route_after_observation,
            {
                "continue": "retrieve_candidates",
                "verify": "verify_constraints",
            },
        )
        builder.add_conditional_edges(
            "generate_answer",
            self.route_after_answer,
            {
                "wait_for_confirmation": "wait_for_confirmation",
                "complete": "complete",
            },
        )
        builder.add_edge("wait_for_confirmation", "complete")
        builder.add_edge("complete", END)
        return builder.compile(checkpointer=self._checkpointer)

    @staticmethod
    def route_after_answer(state: AgentState) -> str:
        return (
            "wait_for_confirmation"
            if state.get("pending_action") or state.get("intent") == "cart_handoff"
            else "complete"
        )

    @staticmethod
    def route_after_observation(state: AgentState) -> str:
        return "continue" if state.get("planned_tool") else "verify"

    def _initial_state(
        self,
        *,
        task_id: str,
        message: str,
        session_id: str,
        image_path: str | None,
        language: str,
        request_id: str | None,
        decision_product_id: str | None,
        trusted_user_id: str | None,
    ) -> AgentState:
        return {
            "task_id": validate_task_id(task_id),
            "request_id": normalize_request_id(request_id),
            "session_id": validate_session_id(session_id),
            "trusted_user_id": trusted_user_id or session_id,
            "trusted_context": bool(trusted_user_id),
            "message": message.strip(),
            "image_path": image_path,
            "language": language,
            "input_fingerprint": self._fingerprint(
                message,
                session_id,
                language,
                bool(image_path),
                decision_product_id,
                trusted_user_id,
            ),
            "context_refs": {},
            "candidate_products": [],
            "tool_results": {},
            "evidence": [],
            "missing_fields": [],
            "fit_risks": [],
            "confidence": 0,
            "pending_action": None,
            "executed_nodes": [],
            "error": None,
            "slots": {},
            "planned_tool": None,
            "planned_arguments": {},
            "react_step": 0,
            "react_max_steps": self.react_max_steps,
            "react_observations": [],
            "react_stop_reason": None,
            "comparison": [],
            "tool_trace": [],
            "node_trace": [],
            "answer": "",
            "answer_streamed": False,
            "status": "new",
            "decision_product_id": decision_product_id,
            "decision": None,
            "wardrobe_snapshot": None,
            "wardrobe_plan": None,
            "skill": None,
        }

    @staticmethod
    def _config(task_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": task_id}}

    def _resume_input(
        self,
        *,
        config: dict[str, dict[str, str]],
        initial: AgentState,
    ) -> tuple[AgentState | None, bool]:
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            return initial, False
        existing = snapshot.values
        if existing.get("input_fingerprint") != initial["input_fingerprint"]:
            raise invalid_input(
                "Task ID is already associated with different input.",
                details={"field": "task_id"},
            )

        replacement_image = initial.get("image_path")
        saved_image = existing.get("image_path")
        if (
            replacement_image
            and replacement_image != saved_image
            and (not saved_image or not Path(saved_image).is_file())
        ):
            planned_arguments = dict(existing.get("planned_arguments", {}))
            if "image_path" in planned_arguments:
                planned_arguments["image_path"] = replacement_image
            self.graph.update_state(
                config,
                {
                    "image_path": replacement_image,
                    "planned_arguments": planned_arguments,
                },
            )
        return None, True

    def invoke(
        self,
        *,
        task_id: str,
        message: str,
        session_id: str,
        image_path: str | None = None,
        language: str = "zh",
        request_id: str | None = None,
        decision_product_id: str | None = None,
        trusted_user_id: str | None = None,
    ) -> AgentResponse:
        response: AgentResponse | None = None
        for item in self.stream(
            task_id=task_id,
            message=message,
            session_id=session_id,
            image_path=image_path,
            language=language,
            request_id=request_id,
            decision_product_id=decision_product_id,
            trusted_user_id=trusted_user_id,
        ):
            if item["type"] == "result":
                response = AgentResponse.model_validate(item["response"])
        if response is None:
            raise RuntimeError("Agent workflow did not produce a response.")
        return response

    def stream(
        self,
        *,
        task_id: str,
        message: str,
        session_id: str,
        image_path: str | None = None,
        language: str = "zh",
        request_id: str | None = None,
        decision_product_id: str | None = None,
        trusted_user_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        task_id = validate_task_id(task_id)
        initial = self._initial_state(
            task_id=task_id,
            message=message,
            session_id=session_id,
            image_path=image_path,
            language=language,
            request_id=request_id,
            decision_product_id=decision_product_id,
            trusted_user_id=trusted_user_id,
        )
        config = self._config(task_id)
        self._cleanup_expired_checkpoints()
        self._register_checkpoint_task(task_id)
        self.orchestrator.memory.register_task(
            task_id, initial["session_id"], initial["trusted_user_id"]
        )
        with self._locks.hold(task_id):
            graph_input, recovered = self._resume_input(
                config=config,
                initial=initial,
            )
            snapshot = self.graph.get_state(config)
            if snapshot.values.get("status") == "completed":
                response = AgentResponse.model_validate(snapshot.values["response"])
                yield {
                    "type": "result",
                    "response": response.model_copy(
                        update={
                            "request_id": initial["request_id"],
                            "recovered": True,
                        }
                    ).to_dict(),
                }
                return

            with telemetry.span(
                "agent.task",
                **{
                    "agent.task_id": task_id,
                    "agent.request_id": initial["request_id"],
                    "agent.recovered": recovered,
                },
            ):
                for part in self.graph.stream(
                    graph_input,
                    config,
                    stream_mode="custom",
                    version="v2",
                ):
                    if part["type"] == "custom":
                        data = part["data"]
                        yield {
                            "type": "token" if "token" in data else "node",
                            "data": data,
                        }

            completed = self.graph.get_state(config)
            if completed.values.get("status") != "completed":
                raise RuntimeError("Agent workflow stopped before completion.")
            response = AgentResponse.model_validate(completed.values["response"])
            self.orchestrator.memory.complete_task(task_id)
            yield {
                "type": "result",
                "response": response.model_copy(
                    update={
                        "request_id": initial["request_id"],
                        "recovered": recovered,
                    }
                ).to_dict(),
            }

    def cancel(self, *, task_id: str, session_id: str, trusted_user_id: str | None) -> bool:
        task_id = validate_task_id(task_id)
        session_id = validate_session_id(session_id)
        state = self.get_task_state(task_id)
        context = self.orchestrator.memory.task_context(task_id)
        if state and state.get("session_id") != session_id:
            raise invalid_input("Task does not belong to this session.", status_code=404)
        if context and context[0] != session_id:
            raise invalid_input("Task does not belong to this session.", status_code=404)
        expected_user_id = state.get("trusted_user_id") if state else (context[1] if context else session_id)
        if state.get("trusted_context") and trusted_user_id != expected_user_id:
            raise invalid_input("Trusted user context is required.", status_code=401)
        if context and context[1] != session_id and trusted_user_id != expected_user_id:
            raise invalid_input("Trusted user context is required.", status_code=401)
        return self.orchestrator.memory.cancel_task(task_id, session_id, expected_user_id)

    def get_task_state(self, task_id: str) -> AgentState:
        config = self._config(validate_task_id(task_id))
        return dict(self.graph.get_state(config).values)

    def get_replay(
        self,
        *,
        task_id: str,
        session_id: str,
        trusted_user_id: str | None,
    ) -> dict[str, Any]:
        """Return a privacy-safe task replay for debugging and evaluation.

        Raw prompts, generated text, images and user body data stay out of the
        replay. The result contains only execution metadata, facts references
        and the structured outcome already returned to the requesting user.
        """
        task_id = validate_task_id(task_id)
        session_id = validate_session_id(session_id)
        state = self.get_task_state(task_id)
        if not state or state.get("session_id") != session_id:
            raise invalid_input(
                "Task does not belong to this session.", status_code=404
            )
        if (
            state.get("trusted_context")
            and state.get("trusted_user_id") != trusted_user_id
        ):
            raise invalid_input("Trusted user context is required.", status_code=401)
        response = state.get("response", {})
        pending = response.get("pending_action") if isinstance(response, dict) else None
        return {
            "task_id": task_id,
            "request_id": state.get("request_id"),
            "status": state.get("status"),
            "intent": state.get("intent"),
            "skill": state.get("skill"),
            "nodes": state.get("node_trace", []),
            "tools": state.get("tool_trace", []),
            "context_refs": state.get("context_refs", {}),
            "evidence": state.get("evidence", []),
            "outcome": {
                "candidate_count": len(state.get("candidate_products", [])),
                "comparison_count": len(state.get("comparison", [])),
                "decision_verdict": (state.get("decision") or {}).get("verdict"),
                "confirmation_required": bool(pending),
            },
        }
