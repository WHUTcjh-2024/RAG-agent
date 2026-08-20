from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from threading import RLock
from typing import Any

from langchain_core.chat_history import InMemoryChatMessageHistory

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException
from app.db.pg import PgConnection, connect as _pg_connect, database_url


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


def validate_session_id(session_id: str) -> str:
    candidate = session_id.strip()
    if not SESSION_ID_PATTERN.fullmatch(candidate):
        raise AgentException(
            ErrorCode.INVALID_SESSION_ID,
            "Session ID must be 1-100 characters using letters, numbers, '.', '_', ':' or '-'.",
            status_code=HTTPStatus.BAD_REQUEST,
            stage="validate_input",
        )
    return candidate


def _read_session_ttl_seconds() -> int:
    configured = os.getenv("SESSION_TTL_SECONDS", "").strip()
    if not configured:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        value = int(configured)
    except ValueError as error:
        raise RuntimeError("SESSION_TTL_SECONDS must be a positive integer.") from error
    if value <= 0:
        raise RuntimeError("SESSION_TTL_SECONDS must be a positive integer.")
    return value


def _auto_setup_enabled() -> bool:
    return os.getenv("AGENT_MEMORY_AUTO_SETUP", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass
class SessionState:
    history: InMemoryChatMessageHistory = field(
        default_factory=InMemoryChatMessageHistory
    )
    slots: dict[str, Any] = field(default_factory=dict)
    last_results: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AgentMemoryStore:
    """Durable agent session state, persisted in PostgreSQL.

    The store is the single source of truth for cancellation, completion and
    session ownership so those guarantees hold across API replicas.
    """

    def __init__(self) -> None:
        configured_backend = os.getenv("AGENT_MEMORY_BACKEND", "postgres").strip().casefold()
        if configured_backend not in {"postgres"}:
            raise RuntimeError("AGENT_MEMORY_BACKEND must be 'postgres'.")
        self._database_url = database_url("AGENT_MEMORY_DATABASE_URL")
        self.session_ttl_seconds = _read_session_ttl_seconds()
        self._sessions: dict[str, SessionState] = {}
        self._cache_enabled = False
        self._lock = RLock()
        self._needs_setup = _auto_setup_enabled()
        if self._needs_setup:
            self.setup()
            self.cleanup_expired()

    def _connect(self) -> PgConnection:
        return _pg_connect("AGENT_MEMORY_DATABASE_URL")

    def setup(self) -> None:
        """Deploy migration entrypoint; API startup uses it only when opted in."""
        timestamp_type = "TIMESTAMPTZ"
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_user_id TEXT,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    slots_json TEXT NOT NULL DEFAULT '{{}}',
                    last_results_json TEXT NOT NULL DEFAULT '[]',
                    updated_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            session_columns = {
                str(row["column_name"])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'agent_sessions'"
                )
            }
            if "owner_user_id" not in session_columns:
                connection.execute(
                    "ALTER TABLE agent_sessions ADD COLUMN owner_user_id TEXT"
                )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS agent_actions (
                    action_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cart_item_id TEXT,
                    expires_at {timestamp_type} NOT NULL,
                    updated_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS agent_task_commits (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    committed_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS agent_task_controls (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    updated_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS agent_sessions_updated_at_idx ON agent_sessions(updated_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS agent_task_controls_session_id_idx ON agent_task_controls(session_id)"
            )

    @staticmethod
    def _serialize_history(state: SessionState) -> list[dict[str, str]]:
        return [
            {
                "role": "user" if item.type == "human" else "assistant",
                "content": str(item.content),
            }
            for item in state.history.messages
        ]

    @staticmethod
    def _state_from_row(row: Any | None) -> SessionState:
        state = SessionState()
        if row is None:
            return state
        for item in json.loads(row["history_json"]):
            if item.get("role") == "user":
                state.history.add_user_message(str(item.get("content", "")))
            else:
                state.history.add_ai_message(str(item.get("content", "")))
        state.slots = json.loads(row["slots_json"])
        state.last_results = json.loads(row["last_results_json"])
        updated_at = row["updated_at"]
        state.updated_at = (
            updated_at
            if isinstance(updated_at, datetime)
            else datetime.strptime(str(updated_at), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        )
        return state

    def _save(self, session_id: str, state: SessionState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        values = (
            session_id,
            json.dumps(self._serialize_history(state), ensure_ascii=False),
            json.dumps(state.slots, ensure_ascii=False),
            json.dumps(state.last_results, ensure_ascii=False),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_sessions
                    (session_id, history_json, slots_json, last_results_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    history_json=excluded.history_json,
                    slots_json=excluded.slots_json,
                    last_results_json=excluded.last_results_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                values,
            )

    def _is_expired(self, state: SessionState) -> bool:
        age = datetime.now(timezone.utc) - state.updated_at
        return age.total_seconds() >= self.session_ttl_seconds

    def cleanup_expired(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self.session_ttl_seconds
        )
        with self._lock:
            expired_cached = [
                session_id
                for session_id, state in self._sessions.items()
                if self._is_expired(state)
            ]
            for session_id in expired_cached:
                self._sessions.pop(session_id, None)
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM agent_sessions WHERE updated_at < ?", (cutoff,)
                )
                connection.execute(
                    "DELETE FROM agent_task_controls WHERE updated_at < ?",
                    (cutoff,),
                )
                connection.execute(
                    "DELETE FROM agent_task_commits WHERE session_id NOT IN (SELECT session_id FROM agent_sessions)"
                )
            return max(cursor.rowcount, 0)

    def register_task(self, task_id: str, session_id: str, user_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_task_controls (task_id, session_id, user_id)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP
                """,
                (task_id, validate_session_id(session_id), user_id),
            )

    def cancel_task(self, task_id: str, session_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_task_controls
                SET status='cancelled', updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND session_id=? AND user_id=? AND status='running'
                """,
                (task_id, validate_session_id(session_id), user_id),
            )
            return cursor.rowcount == 1

    def task_cancelled(self, task_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM agent_task_controls WHERE task_id=?", (task_id,)
            ).fetchone()
        return bool(row and row["status"] == "cancelled")

    def task_context(self, task_id: str) -> tuple[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, user_id FROM agent_task_controls WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return (str(row["session_id"]), str(row["user_id"])) if row else None

    def complete_task(self, task_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_task_controls SET status='completed', updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND status='running'
                """,
                (task_id,),
            )

    @staticmethod
    def _validate_owner_user_id(user_id: str) -> str:
        candidate = user_id.strip()
        if not candidate or len(candidate) > 128:
            raise ValueError("Trusted user ID must be 1-128 characters.")
        return candidate

    def claim_session(self, session_id: str, user_id: str) -> bool:
        """Create a session for an owner or verify its existing ownership.

        Existing rows without an owner predate access control and are deliberately
        not claimable: knowing a legacy session ID is not proof of authorization.
        """
        session_id = validate_session_id(session_id)
        user_id = self._validate_owner_user_id(user_id)
        with self._lock, self._connect() as connection:
            created = connection.execute(
                """
                INSERT INTO agent_sessions(session_id, owner_user_id)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO NOTHING
                RETURNING owner_user_id
                """,
                (session_id, user_id),
            ).fetchone()
            if created is not None:
                return True
            row = connection.execute(
                "SELECT owner_user_id FROM agent_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        owner_user_id = row["owner_user_id"] if row is not None else None
        return owner_user_id is not None and str(owner_user_id) == user_id

    def task_ids_for_owned_session(self, session_id: str, user_id: str) -> list[str] | None:
        session_id = validate_session_id(session_id)
        user_id = self._validate_owner_user_id(user_id)
        with self._connect() as connection:
            owner = connection.execute(
                "SELECT 1 FROM agent_sessions WHERE session_id=? AND owner_user_id=?",
                (session_id, user_id),
            ).fetchone()
            if owner is None:
                return None
            rows = connection.execute(
                "SELECT task_id FROM agent_task_controls WHERE session_id=? AND user_id=?",
                (session_id, user_id),
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def is_session_owned_by(self, session_id: str, user_id: str) -> bool:
        session_id = validate_session_id(session_id)
        user_id = self._validate_owner_user_id(user_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM agent_sessions WHERE session_id=? AND owner_user_id=?",
                (session_id, user_id),
            ).fetchone()
        return row is not None

    def delete_owned_session(self, session_id: str, user_id: str) -> bool:
        session_id = validate_session_id(session_id)
        user_id = self._validate_owner_user_id(user_id)
        with self._lock, self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM agent_sessions WHERE session_id=? AND owner_user_id=?",
                (session_id, user_id),
            )
            if deleted.rowcount != 1:
                return False
            connection.execute(
                """
                DELETE FROM agent_actions
                WHERE task_id IN (
                    SELECT task_id FROM agent_task_controls WHERE session_id=?
                )
                """,
                (session_id,),
            )
            connection.execute("DELETE FROM agent_task_controls WHERE session_id=?", (session_id,))
            connection.execute("DELETE FROM agent_task_commits WHERE session_id=?", (session_id,))
            self._sessions.pop(session_id, None)
            return True

    def delete_session(self, session_id: str) -> None:
        session_id = validate_session_id(session_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM agent_sessions WHERE session_id=?", (session_id,)
            )
            connection.execute(
                "DELETE FROM agent_task_controls WHERE session_id=?", (session_id,)
            )
            connection.execute(
                "DELETE FROM agent_task_commits WHERE session_id=?", (session_id,)
            )
            self._sessions.pop(session_id, None)

    def task_ids_for_session(self, session_id: str) -> list[str]:
        session_id = validate_session_id(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM agent_task_controls WHERE session_id=?",
                (session_id,),
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def get(self, session_id: str) -> SessionState:
        session_id = validate_session_id(session_id)
        with self._lock:
            cached = self._sessions.get(session_id) if self._cache_enabled else None
            if cached is not None and self._is_expired(cached):
                self._sessions.pop(session_id, None)
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM agent_sessions WHERE session_id = ?", (session_id,)
                    )
            if not self._cache_enabled or session_id not in self._sessions:
                with self._connect() as connection:
                    row = connection.execute(
                        "SELECT * FROM agent_sessions WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                state = self._state_from_row(row)
                if self._cache_enabled:
                    self._sessions[session_id] = state
                return state
            return self._sessions[session_id]

    def update_slots(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self.get(session_id)
            for key, value in updates.items():
                if value in (None, "", []):
                    continue
                if key == "avoid":
                    existing = list(state.slots.get("avoid", []))
                    for item in value if isinstance(value, list) else [value]:
                        if item not in existing:
                            existing.append(item)
                    state.slots[key] = existing
                else:
                    state.slots[key] = value
            self._save(session_id, state)
            return dict(state.slots)

    def set_last_results(self, session_id: str, product_ids: list[str]) -> None:
        with self._lock:
            state = self.get(session_id)
            state.last_results = list(product_ids)
            self._save(session_id, state)

    def add_user_message(self, session_id: str, content: str) -> None:
        with self._lock:
            state = self.get(session_id)
            state.history.add_user_message(content)
            self._save(session_id, state)

    def add_ai_message(self, session_id: str, content: str) -> None:
        with self._lock:
            state = self.get(session_id)
            state.history.add_ai_message(content)
            self._save(session_id, state)

    def recent_history(self, session_id: str, limit: int = 8) -> list[dict[str, str]]:
        messages = self.get(session_id).history.messages[-limit:]
        return [
            {
                "role": "user" if message.type == "human" else "assistant",
                "content": str(message.content),
            }
            for message in messages
        ]

    def commit_turn(
        self,
        *,
        task_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        slots: dict[str, Any],
        last_results: list[str],
    ) -> bool:
        """Atomically commit one workflow turn once, even when a node is retried."""
        session_id = validate_session_id(session_id)
        with self._lock, self._connect() as connection:
            claim = connection.execute(
                """
                INSERT INTO agent_task_commits (task_id, session_id)
                VALUES (?, ?)
                ON CONFLICT(task_id) DO NOTHING
                """,
                (task_id, session_id),
            )
            if claim.rowcount != 1:
                return False

            row = connection.execute(
                "SELECT * FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            state = self._state_from_row(row)
            state.history.add_user_message(user_content)
            state.history.add_ai_message(assistant_content)
            state.slots = dict(slots)
            state.last_results = list(last_results)
            connection.execute(
                """
                INSERT INTO agent_sessions
                    (session_id, history_json, slots_json, last_results_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    history_json=excluded.history_json,
                    slots_json=excluded.slots_json,
                    last_results_json=excluded.last_results_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    session_id,
                    json.dumps(self._serialize_history(state), ensure_ascii=False),
                    json.dumps(state.slots, ensure_ascii=False),
                    json.dumps(state.last_results, ensure_ascii=False),
                ),
            )
            state.updated_at = datetime.now(timezone.utc)
            if self._cache_enabled:
                self._sessions[session_id] = state
            return True

    def save_pending_action(
        self, action: dict[str, Any], user_id: str, task_id: str
    ) -> None:
        raw_expires = action["expires_at"]
        expires_at = (
            datetime.fromisoformat(str(raw_expires).replace("Z", "+00:00"))
            if isinstance(raw_expires, str)
            else raw_expires
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_actions (action_id, task_id, user_id, status, expires_at)
                VALUES (?, ?, ?, 'pending', ?)
                ON CONFLICT(action_id) DO NOTHING
                """,
                (action["action_id"], task_id, user_id, expires_at),
            )

    def complete_action(self, action_id: str, user_id: str, cart_item_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_actions
                SET status='completed', cart_item_id=?, updated_at=CURRENT_TIMESTAMP
                WHERE action_id=? AND user_id=? AND status='pending'
                  AND expires_at >= CURRENT_TIMESTAMP
                """,
                (cart_item_id, action_id, user_id),
            )
            return cursor.rowcount == 1
