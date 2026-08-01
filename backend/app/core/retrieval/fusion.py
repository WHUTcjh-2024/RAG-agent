from __future__ import annotations

from collections.abc import Mapping, Sequence


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]], *, rank_constant: int = 60
) -> tuple[dict[str, float], dict[str, dict[str, int]]]:
    """Fuse named ranked lists and retain enough detail for user-visible tracing."""
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive.")
    scores: dict[str, float] = {}
    source_ranks: dict[str, dict[str, int]] = {}
    for source, ranking in rankings.items():
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rank_constant + rank)
            source_ranks.setdefault(item_id, {})[source] = rank
    return scores, source_ranks


def ranked_ids(ids: Sequence[str], scores: Sequence[float]) -> list[str]:
    if len(ids) != len(scores):
        raise ValueError("IDs and scores must have equal lengths.")
    return [
        item_id
        for item_id, _ in sorted(zip(ids, scores), key=lambda item: (-item[1], item[0]))
    ]
