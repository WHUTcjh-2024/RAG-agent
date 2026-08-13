"""One-time deploy migration for LangGraph's Postgres checkpointer tables."""

from __future__ import annotations

import os

from langgraph.checkpoint.postgres import PostgresSaver


def main() -> None:
    database_url = os.getenv("AGENT_CHECKPOINT_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("AGENT_CHECKPOINT_DATABASE_URL is required.")
    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()
    print("agent_checkpoint_schema=ready")


if __name__ == "__main__":
    main()
