from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.text_encoder import DEFAULT_MODEL, create_text_encoder
from app.core.retrieval.bm25 import BM25Index


PROFILE_FIELDS = (
    ("prod_name", "商品名"),
    ("product_type_name", "商品类型"),
    ("product_group_name", "商品大类"),
    ("colour_group_name", "颜色"),
    ("perceived_colour_master_name", "主色系"),
    ("graphical_appearance_name", "图案"),
    ("garment_group_name", "服装组"),
    ("department_name", "部门"),
    ("section_name", "分区"),
    ("detail_desc", "商品描述"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local product text index.")
    parser.add_argument(
        "--input_csv",
        type=Path,
        default=BACKEND_DIR / "data" / "sample" / "articles_sample.csv",
    )
    parser.add_argument(
        "--index_dir",
        type=Path,
        default=BACKEND_DIR / "data" / "vector_store" / "text",
    )
    parser.add_argument(
        "--backend",
        choices=("sentence-transformers", "hashing"),
        default="sentence-transformers",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def build_text_profile(row: dict[str, str]) -> str:
    existing = (row.get("text_profile") or "").strip()
    if existing:
        return existing
    parts = [
        f"{label}：{value.strip()}"
        for field, label in PROFILE_FIELDS
        if (value := row.get(field)) and value.strip()
    ]
    return "\n".join(parts)


def read_products(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "article_id" not in reader.fieldnames:
            raise RuntimeError("Input CSV must contain an article_id column.")
        products = []
        seen: set[str] = set()
        for row in reader:
            article_id = (row.get("article_id") or "").strip()
            if not article_id or article_id in seen:
                continue
            row["article_id"] = (
                article_id.zfill(10) if article_id.isdigit() else article_id
            )
            row["text_profile"] = build_text_profile(row)
            if not row["text_profile"]:
                continue
            products.append(row)
            seen.add(article_id)
    if not products:
        raise RuntimeError("No indexable products found in input CSV.")
    return products


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_index(
    index_dir: Path,
    products: list[dict[str, str]],
    embeddings: np.ndarray,
    lexical_index: BM25Index,
    metadata: dict[str, object],
    force: bool,
) -> None:
    if index_dir.exists() and any(index_dir.iterdir()) and not force:
        raise RuntimeError(
            f"Index directory is not empty: {index_dir}. Use --force to replace it."
        )
    index_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".text_index_", dir=index_dir.parent))
    try:
        np.save(staging / "embeddings.npy", embeddings.astype(np.float32))
        with (staging / "products.jsonl").open("w", encoding="utf-8") as handle:
            for product in products:
                handle.write(json.dumps(product, ensure_ascii=False) + "\n")
        (staging / "bm25.json").write_text(
            json.dumps(lexical_index.to_payload(), ensure_ascii=False), encoding="utf-8"
        )
        (staging / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for name in ("embeddings.npy", "products.jsonl", "bm25.json", "metadata.json"):
            os.replace(staging / name, index_dir / name)
    finally:
        staging.rmdir()


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        raise ValueError("--batch_size must be greater than zero.")
    input_csv = args.input_csv.resolve()
    index_dir = args.index_dir.resolve()

    print(f"[1/4] Reading products: {input_csv}", flush=True)
    products = read_products(input_csv)
    print(f"      indexable products: {len(products):,}", flush=True)

    print(f"[2/4] Loading encoder backend: {args.backend}", flush=True)
    encoder = create_text_encoder(args.backend, args.model)

    print("[3/4] Encoding text profiles", flush=True)
    embeddings = encoder.encode(
        [product["text_profile"] for product in products],
        batch_size=args.batch_size,
    )
    if embeddings.shape != (len(products), encoder.dimension):
        raise RuntimeError(f"Unexpected embedding shape: {embeddings.shape}")

    lexical_index = BM25Index.from_documents(
        product["text_profile"] for product in products
    )
    metadata = {
        "version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend,
        "model": args.model
        if args.backend == "sentence-transformers"
        else "hashing-smoke-test",
        "dimension": encoder.dimension,
        "count": len(products),
        "input_csv": str(input_csv),
        "input_sha256": file_sha256(input_csv),
        "lexical_index": {"file": "bm25.json", "version": 1},
    }
    print(f"[4/4] Writing index: {index_dir}", flush=True)
    # Keep sparse and dense indexes built from the exact same product snapshot.
    write_index(
        index_dir,
        products,
        embeddings,
        lexical_index,
        metadata,
        force=args.force,
    )
    print(f"SUCCESS: indexed {len(products):,} products", flush=True)
    print(
        "NEXT: uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
