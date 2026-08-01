from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import Any, Iterable

import numpy as np


_WORD_RE = re.compile(r"[\w]+", flags=re.UNICODE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese and Latin catalog text without a dictionary dependency."""
    normalized = " ".join(text.casefold().split())
    tokens = _WORD_RE.findall(normalized)
    for run in _CJK_RE.findall(normalized):
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        if len(run) == 1:
            tokens.append(run)
    return tokens


@dataclass(frozen=True)
class BM25Index:
    document_terms: tuple[dict[str, int], ...]
    document_lengths: np.ndarray
    document_frequency: dict[str, int]
    average_document_length: float
    k1: float = 1.2
    b: float = 0.75

    @classmethod
    def from_documents(cls, documents: Iterable[str]) -> "BM25Index":
        term_counts = tuple(dict(Counter(tokenize(document))) for document in documents)
        document_frequency: Counter[str] = Counter()
        for counts in term_counts:
            document_frequency.update(counts.keys())
        lengths = np.asarray(
            [sum(counts.values()) for counts in term_counts], dtype=np.float32
        )
        average_length = float(lengths.mean()) if len(lengths) else 0.0
        return cls(term_counts, lengths, dict(document_frequency), average_length)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BM25Index":
        if payload.get("version") != 1:
            raise RuntimeError("Unsupported BM25 index version.")
        document_terms = payload.get("document_terms")
        document_lengths = payload.get("document_lengths")
        document_frequency = payload.get("document_frequency")
        if not isinstance(document_terms, list) or not isinstance(
            document_lengths, list
        ):
            raise RuntimeError("BM25 index payload is malformed.")
        if len(document_terms) != len(document_lengths):
            raise RuntimeError("BM25 document counts do not match.")
        return cls(
            tuple(
                {str(term): int(count) for term, count in terms.items()}
                for terms in document_terms
            ),
            np.asarray(document_lengths, dtype=np.float32),
            {
                str(term): int(count)
                for term, count in (document_frequency or {}).items()
            },
            float(payload.get("average_document_length") or 0.0),
            float(payload.get("k1") or 1.2),
            float(payload.get("b") or 0.75),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "tokenizer": "unicode_words_plus_cjk_bigrams",
            "k1": self.k1,
            "b": self.b,
            "average_document_length": self.average_document_length,
            "document_lengths": self.document_lengths.astype(float).tolist(),
            "document_frequency": self.document_frequency,
            "document_terms": list(self.document_terms),
        }

    def scores(self, query: str, candidate_indices: np.ndarray) -> np.ndarray:
        terms = tokenize(query)
        if not terms or candidate_indices.size == 0:
            return np.zeros(candidate_indices.size, dtype=np.float32)
        document_count = len(self.document_terms)
        if document_count == 0 or self.average_document_length <= 0:
            return np.zeros(candidate_indices.size, dtype=np.float32)

        query_counts = Counter(terms)
        scores = np.zeros(candidate_indices.size, dtype=np.float32)
        for output_index, document_index in enumerate(candidate_indices):
            counts = self.document_terms[int(document_index)]
            length = float(self.document_lengths[int(document_index)])
            score = 0.0
            for term, query_count in query_counts.items():
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                document_frequency = self.document_frequency.get(term, 0)
                inverse_frequency = math.log(
                    1.0
                    + (document_count - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * length / self.average_document_length
                )
                score += (
                    query_count
                    * inverse_frequency
                    * frequency
                    * (self.k1 + 1.0)
                    / denominator
                )
            scores[output_index] = score
        return scores
