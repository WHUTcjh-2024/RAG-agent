"""Scheduled retention job for Postgres-backed agent session/task state."""

from __future__ import annotations

import os

from app.core.agent.memory import AgentMemoryStore


def main() -> None:
    store = AgentMemoryStore()
    print(f"pruned_agent_sessions={store.cleanup_expired()}")


if __name__ == "__main__":
    main()
