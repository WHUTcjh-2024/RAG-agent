from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.slot_extractor import SlotExtractor
from app.core.retrieval.text_retriever import TextRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval, intent and slot quality."
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
    parser.add_argument("--minimum_recall_at_1", type=float, default=0.70)
    parser.add_argument("--minimum_recall_at_5", type=float, default=0.95)
    parser.add_argument("--minimum_recall_at_10", type=float, default=0.95)
    parser.add_argument("--minimum_mrr_at_10", type=float, default=0.80)
    parser.add_argument("--minimum_ndcg_at_10", type=float, default=0.80)
    parser.add_argument("--minimum_intent_accuracy", type=float, default=0.90)
    parser.add_argument("--minimum_slot_accuracy", type=float, default=0.90)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def ndcg_at_k(result_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    discounted_gain = sum(
        1.0 / math.log2(rank + 1)
        for rank, article_id in enumerate(result_ids[:k], start=1)
        if article_id in relevant_ids
    )
    ideal_count = min(k, len(relevant_ids))
    ideal_gain = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return discounted_gain / ideal_gain if ideal_gain else 0.0


def _require_labeled_cases(
    cases: dict[str, object], catalog: dict[str, dict[str, object]], metadata: dict[str, object]
) -> list[dict[str, object]]:
    """Reject placeholder or mismatched labels instead of measuring self-retrieval."""
    labeled_cases = cases.get("labeled_retrieval")
    if not isinstance(labeled_cases, list) or not labeled_cases:
        raise ValueError("labeled_retrieval must contain independently authored query labels.")

    catalog_binding = cases.get("catalog")
    if not isinstance(catalog_binding, dict):
        raise ValueError("Evaluation cases must declare their catalog binding.")
    expected_sha = catalog_binding.get("input_sha256")
    if expected_sha != metadata.get("input_sha256"):
        raise ValueError(
            "Evaluation cases do not match the indexed catalog snapshot; "
            "rebuild the approved catalog or use its matching labels."
        )
    expected_count = catalog_binding.get("product_count")
    if expected_count != len(catalog):
        raise ValueError("Evaluation case catalog product_count does not match the index.")

    profiles = {
        " ".join(str(product.get("text_profile", "")).split()).casefold()
        for product in catalog.values()
    }
    validated: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for position, case in enumerate(labeled_cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"labeled_retrieval item {position} must be an object.")
        case_id = case.get("id")
        query = case.get("query")
        relevant_ids = case.get("relevant_ids")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError(f"labeled_retrieval item {position} has an invalid or duplicate id.")
        if not isinstance(query, str) or len(query.strip()) < 8:
            raise ValueError(f"labeled_retrieval item {case_id} needs a substantive query.")
        normalized_query = " ".join(query.split()).casefold()
        if normalized_query in profiles:
            raise ValueError(f"labeled_retrieval item {case_id} repeats a catalog text profile.")
        if not isinstance(relevant_ids, list) or not relevant_ids:
            raise ValueError(f"labeled_retrieval item {case_id} needs relevant_ids.")
        if not all(isinstance(article_id, str) and article_id in catalog for article_id in relevant_ids):
            raise ValueError(f"labeled_retrieval item {case_id} references a missing catalog product.")
        filters = case.get("filters", {})
        if not isinstance(filters, dict):
            raise ValueError(f"labeled_retrieval item {case_id} filters must be an object.")
        validated.append({
            "id": case_id,
            "query": query,
            "relevant_ids": list(dict.fromkeys(relevant_ids)),
            "filters": filters,
        })
        seen_ids.add(case_id)
    return validated


def _evaluate_retrieval_cases(
    retriever: TextRetriever, labeled_cases: list[dict[str, object]]
) -> tuple[list[int | None], list[float], list[float], list[dict[str, object]]]:
    ranks: list[int | None] = []
    latencies: list[float] = []
    ndcgs: list[float] = []
    case_results: list[dict[str, object]] = []
    for case in labeled_cases:
        relevant_ids = set(case["relevant_ids"])
        started = time.perf_counter()
        results, _ = retriever.search(
            str(case["query"]), top_k=10, filters=case["filters"]
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        result_ids = [str(item["article_id"]) for item in results]
        first_rank = next(
            (
                rank
                for rank, article_id in enumerate(result_ids, start=1)
                if article_id in relevant_ids
            ),
            None,
        )
        case_ndcg = ndcg_at_k(result_ids, relevant_ids)
        ranks.append(first_rank)
        ndcgs.append(case_ndcg)
        case_results.append({
            "id": case["id"],
            "query": case["query"],
            "relevant_ids": sorted(relevant_ids),
            "returned_ids": result_ids,
            "first_relevant_rank": first_rank,
            "ndcg_at_10": case_ndcg,
            "latency_ms": round(latency_ms, 3),
        })
    return ranks, latencies, ndcgs, case_results


def evaluate(
    *,
    cases: dict[str, object],
    retriever: TextRetriever,
) -> dict[str, object]:
    """Compute reproducible quality gates from catalog-bound independent labels."""
    catalog = {str(item["article_id"]): item for item in retriever.products}
    labeled_cases = _require_labeled_cases(cases, catalog, retriever.metadata)
    ranks, latencies, ndcgs, case_results = _evaluate_retrieval_cases(
        retriever, labeled_cases
    )
    intent_cases = cases.get("intent", [])
    slot_cases = cases.get("slots", [])
    if not isinstance(intent_cases, list) or not isinstance(slot_cases, list):
        raise ValueError("Evaluation intent and slots cases must be arrays.")
    intent_hits = sum(
        ShoppingAgentOrchestrator.classify_intent(message, has_image) == expected
        for message, has_image, expected in intent_cases
    )
    extractor = SlotExtractor()
    slot_hits = sum(
        all(extractor.extract(message).get(key) == value for key, value in expected.items())
        for message, expected in slot_cases
    )
    total_retrieval = len(ranks)
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": total_retrieval + len(intent_cases) + len(slot_cases),
        "retrieval": {
            "evaluation_source": "labeled_retrieval",
            "catalog_input_sha256": retriever.metadata.get("input_sha256"),
            "cases": total_retrieval,
            "recall_at_1": sum(rank == 1 for rank in ranks) / total_retrieval,
            "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks)
            / total_retrieval,
            "recall_at_10": sum(rank is not None for rank in ranks) / total_retrieval,
            "mrr_at_10": sum(1 / rank for rank in ranks if rank) / total_retrieval,
            "ndcg_at_10": sum(ndcgs) / total_retrieval,
            "missing_article_ids": [],
            "latency_ms_p50": statistics.median(latencies),
            "latency_ms_p95": percentile(latencies, 0.95),
            "case_results": case_results,
        },
        "intent_accuracy": intent_hits / len(intent_cases),
        "slot_accuracy": slot_hits / len(slot_cases),
    }


def main() -> int:
    args = parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    retriever = TextRetriever(args.text_index)
    report = evaluate(cases=cases, retriever=retriever)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    thresholds_ok = (
        report["retrieval"]["recall_at_1"] >= args.minimum_recall_at_1
        and report["retrieval"]["recall_at_5"] >= args.minimum_recall_at_5
        and report["retrieval"]["recall_at_10"] >= args.minimum_recall_at_10
        and report["retrieval"]["mrr_at_10"] >= args.minimum_mrr_at_10
        and report["retrieval"]["ndcg_at_10"] >= args.minimum_ndcg_at_10
        and report["intent_accuracy"] >= args.minimum_intent_accuracy
        and report["slot_accuracy"] >= args.minimum_slot_accuracy
    )
    return 0 if thresholds_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
