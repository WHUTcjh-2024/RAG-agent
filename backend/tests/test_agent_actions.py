from __future__ import annotations

# ruff: noqa: E402

import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.actions import create_cart_confirmation
from app.core.agent.memory import AgentMemoryStore
from tests.postgres_helpers import require_postgres


def test_cart_confirmation_is_signed_and_recorded_once(tmp_path: Path, monkeypatch) -> None:
    require_postgres("AGENT_MEMORY_DATABASE_URL")
    monkeypatch.setenv("AGENT_MEMORY_AUTO_SETUP", "true")
    monkeypatch.setenv("AGENT_ACTION_SECRET", "test-agent-action-secret")
    action = create_cart_confirmation(
        task_id="task-1",
        user_id="user-1",
        product={"article_id": "0000000001", "prod_name": "Red Shirt", "price": 19.9},
        language="zh",
    )
    assert action["action_type"] == "ADD_CART_ITEM"
    assert action["confirmation_token"].count(".") == 1

    memory = AgentMemoryStore()
    memory.save_pending_action(action, "user-1", "task-1")
    assert memory.complete_action(action["action_id"], "user-1", "cart-item-1")
    assert not memory.complete_action(action["action_id"], "user-1", "cart-item-1")
