from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.evaluation import (
    AgentEvaluationRunner,
    configured_llm_judge,
    percentile,
    summarize_task_traces,
)
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.slot_extractor import SlotExtractor
from app.core.retrieval.text_retriever import TextRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate labeled catalog retrieval and executable agent tasks."
    )
    parser.add_argument(
        "--cases", type=Path, default=BACKEND_DIR / "evaluation" / "cases.json"
    )
    parser.add_argument(
        "--text_index",
        type=Path,
        default=BACKEND_DIR / "data" / "vector_store" / "text",
    )
    parser.add_argument(
        "--report", type=Path, default=BACKEND_DIR / "evaluation" / "report.json"
    )
    parser.add_argument("--minimum_recall_at_5", type=float, default=0.90)
    parser.add_argument("--minimum_recall_at_10", type=float, default=0.85)
    parser.add_argument("--minimum_ndcg_at_10", type=float, default=0.65)
    parser.add_argument("--minimum_intent_accuracy", type=float, default=0.90)
    parser.add_argument("--minimum_slot_accuracy", type=float, default=0.90)
    parser.add_argument("--minimum_task_success_rate", type=float, default=0.95)
    parser.add_argument("--minimum_tool_argument_accuracy", type=float, default=0.95)
    parser.add_argument("--minimum_fact_citation_coverage", type=float, default=1.0)
    parser.add_argument("--minimum_refusal_injection_pass_rate", type=float, default=1.0)
    parser.add_argument("--minimum_business_execution_pass_rate", type=float, default=1.0)
    parser.add_argument("--maximum_task_latency_ms_p95", type=float, default=2_500)
    parser.add_argument("--maximum_estimated_cost_usd", type=float, default=0.50)
    parser.add_argument(
        "--llm-judge",
        choices=("off", "auto", "required"),
        default="auto",
        help="Use EVAL_LLM_JUDGE_* credentials for subjective quality evaluation.",
    )
    parser.add_argument("--minimum_llm_judge_pass_rate", type=float, default=0.80)
    return parser.parse_args()


def ndcg_at_k(result_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    discounted_gain = sum(
        1.0 / math.log2(rank + 1)
        for rank, article_id in enumerate(result_ids[:k], start=1)
        if article_id in relevant_ids
    )
    ideal_count = min(k, len(relevant_ids))
    ideal_gain = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return discounted_gain / ideal_gain if ideal_gain else 0.0


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _configuration_error(args: argparse.Namespace, message: str) -> int:
    _write_report(
        args.report,
        {
            "schema_version": 2,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "status": "invalid_evaluation_configuration",
            "error": message,
        },
    )
    return 2


def _evaluate_retrieval(
    *, retriever: TextRetriever, labeled_cases: list[dict[str, Any]], catalog: dict[str, Any]
) -> dict[str, Any]:
    ranks: list[int | None] = []
    latencies: list[float] = []
    ndcgs: list[float] = []
    missing: list[str] = []
    for case in labeled_cases:
        relevant_ids = {str(article_id) for article_id in case["relevant_ids"]}
        missing.extend(sorted(relevant_ids - set(catalog)))
        started = time.perf_counter()
        results, _ = retriever.search(
            str(case["query"]), top_k=10, filters=case.get("filters") or {}
        )
        latencies.append((time.perf_counter() - started) * 1000)
        result_ids = [str(item["article_id"]) for item in results]
        ranks.append(
            next(
                (
                    rank
                    for rank, article_id in enumerate(result_ids, start=1)
                    if article_id in relevant_ids
                ),
                None,
            )
        )
        ndcgs.append(ndcg_at_k(result_ids, relevant_ids))
    total = len(ranks)
    return {
        "evaluation_source": "explicit_labeled_catalog_cases",
        "cases": total,
        "recall_at_1": sum(rank == 1 for rank in ranks) / total,
        "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks) / total,
        "recall_at_10": sum(rank is not None for rank in ranks) / total,
        "mrr_at_10": sum(1 / rank for rank in ranks if rank) / total,
        "ndcg_at_10": sum(ndcgs) / total,
        "missing_labeled_article_ids": sorted(set(missing)),
        "latency_ms_p50": statistics.median(latencies),
        "latency_ms_p95": percentile(latencies, 0.95),
    }


def main() -> int:
    args = parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    labeled_cases = list(cases.get("labeled_retrieval") or [])
    task_cases = list(cases.get("task_execution") or [])
    if not labeled_cases:
        return _configuration_error(
            args,
            "labeled_retrieval must contain explicit relevance labels; catalog self-retrieval is not a valid evaluation.",
        )
    if not task_cases:
        return _configuration_error(args, "task_execution must contain executable agent cases.")

    retriever = TextRetriever(args.text_index)
    expected_snapshot = dict(cases.get("catalog_snapshot") or {})
    index_snapshot = str(retriever.metadata.get("input_sha256") or "")
    if expected_snapshot.get("input_sha256") and (
        expected_snapshot["input_sha256"] != index_snapshot
    ):
        return _configuration_error(
            args,
            "Catalog snapshot differs from the labeled benchmark; refresh labels before evaluating this index.",
        )

    judge, judge_status = configured_llm_judge(args.llm_judge)
    if args.llm_judge == "required" and judge is None:
        return _configuration_error(
            args,
            "LLM judge is required but EVAL_LLM_JUDGE_API_KEY and EVAL_LLM_JUDGE_MODEL are not configured.",
        )

    catalog = {str(item["article_id"]): item for item in retriever.products}
    retrieval = _evaluate_retrieval(
        retriever=retriever, labeled_cases=labeled_cases, catalog=catalog
    )
    intent_cases = list(cases.get("intent") or [])
    slot_cases = list(cases.get("slots") or [])
    if not intent_cases or not slot_cases:
        return _configuration_error(args, "intent and slots fixtures must not be empty.")
    intent_hits = sum(
        ShoppingAgentOrchestrator.classify_intent(message, has_image) == expected
        for message, has_image, expected in intent_cases
    )
    extractor = SlotExtractor()
    slot_hits = sum(
        all(extractor.extract(message).get(key) == value for key, value in expected.items())
        for message, expected in slot_cases
    )
    traces = AgentEvaluationRunner(retriever).run(task_cases, judge=judge)
    task_execution = summarize_task_traces(traces)
    judge_metrics = task_execution["llm_judge"]
    judge_metrics.update(
        {
            "status": judge_status,
            "model": getattr(judge, "model", None),
            "required": args.llm_judge == "required",
        }
    )
    report = {
        "schema_version": 2,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "case_count": len(labeled_cases) + len(intent_cases) + len(slot_cases) + len(task_cases),
        "catalog_snapshot": {
            "input_sha256": index_snapshot,
            "label_snapshot_sha256": expected_snapshot.get("input_sha256"),
            "matches_labels": not expected_snapshot.get("input_sha256")
            or expected_snapshot.get("input_sha256") == index_snapshot,
        },
        "retrieval": retrieval,
        "intent_accuracy": intent_hits / len(intent_cases),
        "slot_accuracy": slot_hits / len(slot_cases),
        "task_execution": task_execution,
        "traces": [trace.to_dict() for trace in traces],
    }
    _write_report(args.report, report)
    thresholds_ok = (
        not retrieval["missing_labeled_article_ids"]
        and retrieval["recall_at_5"] >= args.minimum_recall_at_5
        and retrieval["recall_at_10"] >= args.minimum_recall_at_10
        and retrieval["ndcg_at_10"] >= args.minimum_ndcg_at_10
        and report["intent_accuracy"] >= args.minimum_intent_accuracy
        and report["slot_accuracy"] >= args.minimum_slot_accuracy
        and task_execution["success_rate"] >= args.minimum_task_success_rate
        and task_execution["tool_argument_accuracy"] >= args.minimum_tool_argument_accuracy
        and task_execution["fact_citation_coverage"]
        >= args.minimum_fact_citation_coverage
        and task_execution["refusal_injection_pass_rate"]
        >= args.minimum_refusal_injection_pass_rate
        and task_execution["business_execution_pass_rate"]
        >= args.minimum_business_execution_pass_rate
        and task_execution["latency_ms_p95"] <= args.maximum_task_latency_ms_p95
        and task_execution["estimated_cost_usd"] <= args.maximum_estimated_cost_usd
    )
    if args.llm_judge == "required":
        thresholds_ok = thresholds_ok and (
            judge_metrics["cases"] > 0
            and judge_metrics["errors"] == 0
            and judge_metrics["pass_rate"] is not None
            and judge_metrics["pass_rate"] >= args.minimum_llm_judge_pass_rate
        )
    return 0 if thresholds_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
