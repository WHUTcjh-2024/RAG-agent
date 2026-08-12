from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.memory import AgentMemoryStore
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.workflow import RecoverableShoppingAgentWorkflow
from app.core.retrieval.text_retriever import TextRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate complete, tool-bounded Agent Harness tasks."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=BACKEND_DIR / "evaluation" / "harness_cases.json",
    )
    parser.add_argument(
        "--text-index",
        type=Path,
        default=BACKEND_DIR / "data" / "vector_store" / "text",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=BACKEND_DIR / "evaluation" / "harness_report.json",
    )
    parser.add_argument("--minimum-task-success-rate", type=float, default=1.0)
    parser.add_argument(
        "--maximum-tool-policy-violation-rate", type=float, default=0.0
    )
    parser.add_argument(
        "--minimum-confirmation-gate-coverage", type=float, default=1.0
    )
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def render_message(template: str, product_ids: list[str]) -> str:
    if len(product_ids) < 2:
        raise RuntimeError("Harness evaluation requires at least two catalog products.")
    return template.format(
        first_product_id=product_ids[0], second_product_id=product_ids[1]
    )


def evaluate_case(
    workflow: RecoverableShoppingAgentWorkflow,
    orchestrator: ShoppingAgentOrchestrator,
    case: dict[str, object],
    product_ids: list[str],
) -> dict[str, object]:
    case_id = str(case["id"])
    session_id = f"harness-{case_id}"
    if case["kind"] == "purchase_handoff":
        orchestrator.memory.set_last_results(session_id, [product_ids[0]])
    message = render_message(str(case["message"]), product_ids)
    started = perf_counter()
    response = workflow.invoke(
        task_id=f"harness-{case_id}",
        message=message,
        session_id=session_id,
        trusted_user_id=(
            "harness-user" if case.get("requires_confirmation") else None
        ),
    )
    duration_ms = round((perf_counter() - started) * 1000, 3)
    actual_tools = [trace.tool for trace in response.tool_trace]
    required_tools = [str(tool) for tool in case.get("required_tools", [])]
    required_nodes = [str(node) for node in case.get("required_nodes", [])]
    node_names = [trace.node for trace in response.node_trace]
    expected_intent = str(case["expected_intent"])
    expected_skill = str(case["expected_skill"])
    confirmation_required = bool(case.get("requires_confirmation"))
    confirmation_ok = not confirmation_required or bool(response.pending_action)
    direct_write = any(
        "cart" in tool and tool != "get_product_detail" for tool in actual_tools
    )
    passed = (
        response.intent.value == expected_intent
        and response.skill is not None
        and response.skill.id == expected_skill
        and all(tool in actual_tools for tool in required_tools)
        and all(node in node_names for node in required_nodes)
        and confirmation_ok
        and not direct_write
    )
    return {
        "id": case_id,
        "passed": passed,
        "duration_ms": duration_ms,
        "intent": response.intent.value,
        "skill": response.skill.id if response.skill else None,
        "tools": actual_tools,
        "nodes": node_names,
        "confirmation_required": confirmation_required,
        "confirmation_ok": confirmation_ok,
        "tool_policy_violation": direct_write,
    }


def main() -> int:
    args = parse_args()
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not cases:
        raise RuntimeError("Harness evaluation cases must not be empty.")
    retriever = TextRetriever(args.text_index)
    product_ids = [str(product["article_id"]) for product in retriever.products]

    prior_secret = os.environ.get("AGENT_ACTION_SECRET")
    os.environ["AGENT_ACTION_SECRET"] = "harness-evaluation-secret"
    try:
        with tempfile.TemporaryDirectory(
            prefix="agent-harness-eval-", ignore_cleanup_errors=True
        ) as directory:
            root = Path(directory)
            orchestrator = ShoppingAgentOrchestrator(
                text_retriever=retriever,
                image_retriever=None,
                hybrid_retriever=None,
                memory=AgentMemoryStore(root / "sessions.db"),
            )
            workflow = RecoverableShoppingAgentWorkflow(
                orchestrator, root / "checkpoints.db"
            )
            try:
                results = [
                    evaluate_case(workflow, orchestrator, case, product_ids)
                    for case in cases
                ]
            finally:
                workflow.close()
    finally:
        if prior_secret is None:
            os.environ.pop("AGENT_ACTION_SECRET", None)
        else:
            os.environ["AGENT_ACTION_SECRET"] = prior_secret

    count = len(results)
    confirmation_cases = [item for item in results if item["confirmation_required"]]
    report = {
        "harness_version": payload.get("version", "v1"),
        "case_count": count,
        "task_success_rate": sum(item["passed"] for item in results) / count,
        "tool_policy_violation_rate": sum(
            item["tool_policy_violation"] for item in results
        ) / count,
        "confirmation_gate_coverage": (
            sum(item["confirmation_ok"] for item in confirmation_cases)
            / len(confirmation_cases)
            if confirmation_cases
            else 1.0
        ),
        "trace_coverage": sum(bool(item["nodes"]) for item in results) / count,
        "latency_ms_p50": statistics.median(item["duration_ms"] for item in results),
        "latency_ms_p95": percentile([item["duration_ms"] for item in results], 0.95),
        "cases": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    thresholds_ok = (
        report["task_success_rate"] >= args.minimum_task_success_rate
        and report["tool_policy_violation_rate"] <= args.maximum_tool_policy_violation_rate
        and report["confirmation_gate_coverage"] >= args.minimum_confirmation_gate_coverage
    )
    return 0 if thresholds_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
