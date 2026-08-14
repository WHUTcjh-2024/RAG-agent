"""One-time deploy migration for Postgres-backed agent session/task state."""

from __future__ import annotations

import os

from app.core.agent.memory import AgentMemoryStore


def main() -> None:
    if os.getenv("AGENT_MEMORY_BACKEND", "").strip().casefold() != "postgres":
        raise SystemExit(
            "Set AGENT_MEMORY_BACKEND=postgres before running this migration."
        )
    # Store construction performs retention cleanup. Bootstrap schema first so
    # a fresh Postgres database can execute this migration safely.
    os.environ["AGENT_MEMORY_AUTO_SETUP"] = "true"
    AgentMemoryStore().setup()
    print("agent_memory_schema=ready")


if __name__ == "__main__":
    main()
