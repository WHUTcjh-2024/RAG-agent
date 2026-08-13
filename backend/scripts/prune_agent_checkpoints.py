"""Scheduled retention job for the local SQLite development checkpointer.

Production Postgres retention is intentionally executed by the deployment
platform/DB scheduler so API replicas never compete to delete checkpoint rows.
"""

from __future__ import annotations

import os

from app.api.chat import get_orchestrator
from app.core.agent.workflow import RecoverableShoppingAgentWorkflow


def main() -> None:
    backend = os.getenv("AGENT_CHECKPOINT_BACKEND", "sqlite").strip().casefold()
    if backend != "sqlite":
        raise SystemExit(
            "Postgres retention must be configured as a database scheduled job; "
            "this script is SQLite-only."
        )
    workflow = RecoverableShoppingAgentWorkflow(get_orchestrator())
    try:
        print(f"pruned_checkpoints={workflow.prune_expired_checkpoints()}")
    finally:
        workflow.close()


if __name__ == "__main__":
    main()
