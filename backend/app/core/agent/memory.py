from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from threading import RLock
from typing import Any

from langchain_core.chat_history import InMemoryChatMessageHistory

from app.core.agent.contracts import ErrorCode
from app.core.agent.errors import AgentException


DEFAULT_SESSION_DB = (
    Path(__file__).resolve().parents[3] / "data" / "sqlite" / "sessions.db"
)
DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
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


@dataclass
class SessionState:
    history: InMemoryChatMessageHistory = field(default_factory=InMemoryChatMessageHistory)
    slots: dict[str, Any] = field(default_factory=dict)
    last_results: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AgentMemoryStore:
    """Thread-safe session memory backed by SQLite for restart persistence."""

    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        configured = os.getenv("SESSION_DB_PATH", "").strip()
        self.sqlite_path = Path(sqlite_path or configured or DEFAULT_SESSION_DB).resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_ttl_seconds = _read_session_ttl_seconds()
        self._sessions: dict[str, SessionState] = {}
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    slots_json TEXT NOT NULL DEFAULT '{}',
                    last_results_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        self.cleanup_expired()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize_history(state: SessionState) -> list[dict[str, str]]:
        return [
            {"role": "user" if item.type == "human" else "assistant", "content": str(item.content)}
            for item in state.history.messages
        ]

    @staticmethod
    def _state_from_row(row: sqlite3.Row | None) -> SessionState:
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
        state.updated_at = datetime.strptime(
            row["updated_at"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
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
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.session_ttl_seconds)
        cutoff_value = cutoff.strftime("%Y-%m-%d %H:%M:%S")
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
                    "DELETE FROM agent_sessions WHERE updated_at < ?", (cutoff_value,)
                )
            return max(cursor.rowcount, 0)

    def get(self, session_id: str) -> SessionState:
        session_id = validate_session_id(session_id)
        with self._lock:
            cached = self._sessions.get(session_id)
            if cached is not None and self._is_expired(cached):
                self._sessions.pop(session_id, None)
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM agent_sessions WHERE session_id = ?", (session_id,)
                    )
            if session_id not in self._sessions:
                with self._connect() as connection:
                    row = connection.execute(
                        "SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)
                    ).fetchone()
                self._sessions[session_id] = self._state_from_row(row)
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
