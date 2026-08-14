from __future__ import annotations

# ruff: noqa: E402

import json
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.evaluate_recommendations import evaluate


def run_evaluation(index_dir: Path, report_path: Path, cases_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "evaluate_recommendations.py"),
            "--text_index", str(index_dir),
            "--report", str(report_path),
            "--cases", str(cases_path),
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )


def test_evaluation_requires_independent_catalog_bound_labels() -> None:
    source_cases = json.loads((BACKEND_DIR / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    source_cases["labeled_retrieval"] = []

    class UnusedRetriever:
        products: list[dict[str, str]] = []
        metadata: dict[str, str] = {}

    with pytest.raises(ValueError, match="independently authored query labels"):
        evaluate(cases=source_cases, retriever=UnusedRetriever())  # type: ignore[arg-type]


def test_evaluation_rejects_labels_from_another_catalog_snapshot(tmp_path: Path) -> None:
    demo_csv = BACKEND_DIR / "data" / "tianchi-demo" / "articles_sample.csv"
    index_dir = tmp_path / "demo-index"
    build = subprocess.run(
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "build_text_index.py"),
            "--input_csv", str(demo_csv),
            "--index_dir", str(index_dir),
            "--backend", "hashing",
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    cases = json.loads((BACKEND_DIR / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    cases["catalog"]["input_sha256"] = "different-catalog"

    from app.core.retrieval.text_retriever import TextRetriever

    with pytest.raises(ValueError, match="do not match the indexed catalog snapshot"):
        evaluate(cases=cases, retriever=TextRetriever(index_dir))


def test_evaluation_report_includes_per_case_evidence(tmp_path: Path) -> None:
    demo_csv = BACKEND_DIR / "data" / "tianchi-demo" / "articles_sample.csv"
    index_dir = tmp_path / "demo-index"
    build = subprocess.run(
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "build_text_index.py"),
            "--input_csv", str(demo_csv),
            "--index_dir", str(index_dir),
            "--backend", "hashing",
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    report_path = tmp_path / "report.json"
    completed = run_evaluation(index_dir, report_path, BACKEND_DIR / "evaluation" / "cases.json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    retrieval = report["retrieval"]
    assert retrieval["evaluation_source"] == "labeled_retrieval"
    assert len(retrieval["case_results"]) == 10
    assert all(case["first_relevant_rank"] is not None for case in retrieval["case_results"])
