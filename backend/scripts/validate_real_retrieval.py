from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.retrieval.hybrid_retriever import HybridRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate hybrid retrieval on a real catalog."
    )
    parser.add_argument(
        "--catalog_csv",
        "--sample_csv",
        dest="catalog_csv",
        type=Path,
        required=True,
        help="Normalized catalog CSV; --sample_csv is retained as a compatibility alias.",
    )
    parser.add_argument("--text_index_dir", type=Path, required=True)
    parser.add_argument("--image_index_dir", type=Path, required=True)
    parser.add_argument("--report_path", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def select_query_product(catalog_csv: Path) -> tuple[dict[str, str], Path]:
    with catalog_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            relative = (row.get("image_path") or "").replace("/", "\\")
            image_path = (catalog_csv.parent / relative).resolve()
            if image_path.is_file() and (row.get("article_id") or "").strip():
                return row, image_path
    raise RuntimeError("No catalog product with an existing image was found.")


def main() -> int:
    args = parse_args()
    catalog_csv = args.catalog_csv.resolve()
    product, image_path = select_query_product(catalog_csv)
    query_parts = [
        product.get("prod_name", ""),
        product.get("product_type_name", ""),
        product.get("colour_group_name", ""),
        product.get("detail_desc", ""),
    ]
    query = " ".join(part.strip() for part in query_parts if part and part.strip())
    if not query:
        raise RuntimeError("Selected product has no usable text query fields.")
    filters: dict[str, str] = {}
    if product.get("product_type_name"):
        filters["product_type_name"] = product["product_type_name"]

    retriever = HybridRetriever(
        text_index_dir=args.text_index_dir,
        image_index_dir=args.image_index_dir,
        image_device=args.device,
    )
    with Image.open(image_path) as source:
        source.load()
        results, total_candidates = retriever.search(
            query=query,
            image=source.convert("RGB"),
            top_k=5,
            filters=filters,
        )

    article_id = product["article_id"]
    rank = next(
        (
            index
            for index, result in enumerate(results, start=1)
            if result["article_id"] == article_id
        ),
        None,
    )
    if rank is None:
        raise RuntimeError(
            f"Catalog validation failed: query product {article_id} is not in top 5."
        )
    report = {
        "status": "passed",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_csv": str(catalog_csv),
        "query_article_id": article_id,
        "query_image": str(image_path),
        "query": query,
        "filters": filters,
        "total_candidates": total_candidates,
        "self_match_rank": rank,
        "top_results": results,
    }
    report_path = args.report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"SUCCESS: catalog integration report written to {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
