from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from langchain_core.chat_history import InMemoryChatMessageHistory


DEFAULT_SESSION_DB = (
    Path(__file__).resolve().parents[3] / "data" / "sqlite" / "sessions.db"
)


@dataclass
class SessionState:
    history: InMemoryChatMessageHistory = field(default_factory=InMemoryChatMessageHistory)
    slots: dict[str, Any] = field(default_factory=dict)
    last_results: list[str] = field(default_factory=list)


class AgentMemoryStore:
    """Thread-safe session memory backed by SQLite for restart persistence."""

    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        configured = os.getenv("SESSION_DB_PATH", "").strip()
        self.sqlite_path = Path(sqlite_path or configured or DEFAULT_SESSION_DB).resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
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
        return state

    def _save(self, session_id: str, state: SessionState) -> None:
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

    def get(self, session_id: str) -> SessionState:
        with self._lock:
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
