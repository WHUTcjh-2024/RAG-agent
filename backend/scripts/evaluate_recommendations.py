from __future__ import annotations

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


def main() -> int:
    args = parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    retriever = TextRetriever(args.text_index)
    catalog = {str(item["article_id"]): item for item in retriever.products}
    labeled_cases = cases.get("labeled_retrieval", [])
    ranks: list[int | None] = []
    latencies: list[float] = []
    missing: list[str] = []
    ndcgs: list[float] = []
    if labeled_cases:
        for case in labeled_cases:
            relevant_ids = {str(article_id) for article_id in case["relevant_ids"]}
            started = time.perf_counter()
            results, _ = retriever.search(
                case["query"], top_k=10, filters=case.get("filters") or {}
            )
            latencies.append((time.perf_counter() - started) * 1000)
            result_ids = [str(item["article_id"]) for item in results]
            first_rank = next(
                (
                    rank
                    for rank, article_id in enumerate(result_ids, start=1)
                    if article_id in relevant_ids
                ),
                None,
            )
            ranks.append(first_rank)
            ndcgs.append(ndcg_at_k(result_ids, relevant_ids))
        evaluation_source = "labeled_retrieval"
    else:
        for article_id in cases["catalog_self_retrieval"]:
            product = catalog.get(article_id)
            if not product:
                missing.append(article_id)
                ranks.append(None)
                continue
            started = time.perf_counter()
            results, _ = retriever.search(product["text_profile"], top_k=10)
            latencies.append((time.perf_counter() - started) * 1000)
            ids = [str(item["article_id"]) for item in results]
            ranks.append(ids.index(article_id) + 1 if article_id in ids else None)
            ndcgs.append(ndcg_at_k(ids, {article_id}))
        evaluation_source = "catalog_self_retrieval"

    intent_hits = sum(
        ShoppingAgentOrchestrator.classify_intent(message, has_image) == expected
        for message, has_image, expected in cases["intent"]
    )
    extractor = SlotExtractor()
    slot_hits = 0
    for message, expected in cases["slots"]:
        actual = extractor.extract(message)
        slot_hits += all(actual.get(key) == value for key, value in expected.items())

    total_retrieval = len(ranks)
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": total_retrieval + len(cases["intent"]) + len(cases["slots"]),
        "retrieval": {
            "evaluation_source": evaluation_source,
            "cases": total_retrieval,
            "recall_at_1": sum(rank == 1 for rank in ranks) / total_retrieval,
            "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks)
            / total_retrieval,
            "recall_at_10": sum(rank is not None for rank in ranks) / total_retrieval,
            "mrr_at_10": sum(1 / rank for rank in ranks if rank) / total_retrieval,
            "ndcg_at_10": sum(ndcgs) / total_retrieval,
            "missing_article_ids": missing,
            "latency_ms_p50": statistics.median(latencies),
            "latency_ms_p95": percentile(latencies, 0.95),
        },
        "intent_accuracy": intent_hits / len(cases["intent"]),
        "slot_accuracy": slot_hits / len(cases["slots"]),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    thresholds_ok = (
        report["retrieval"]["recall_at_5"] >= 0.90
        and report["retrieval"]["recall_at_10"] >= 0.85
        and report["retrieval"]["ndcg_at_10"] >= 0.65
        and report["intent_accuracy"] >= 0.90
        and report["slot_accuracy"] >= 0.90
    )
    return 0 if thresholds_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
