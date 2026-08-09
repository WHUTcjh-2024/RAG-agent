from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from data_utils import DEFAULT_CATALOG_DIR, read_csv, resolve_image_path, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the normalized Tianchi catalog.")
    parser.add_argument(
        "--input_csv", type=Path, default=DEFAULT_CATALOG_DIR / "articles_sample.csv"
    )
    parser.add_argument(
        "--image_root",
        type=Path,
        default=None,
        help="Defaults to the input CSV directory.",
    )
    parser.add_argument(
        "--report_path", type=Path, default=DEFAULT_CATALOG_DIR / "inspection_report.json"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = args.input_csv.resolve()
    image_root = (args.image_root or input_csv.parent).resolve()
    print(f"[1/4] Reading: {input_csv}", flush=True)
    fields, rows = read_csv(input_csv)
    print(f"      rows={len(rows):,}, fields={len(fields)}", flush=True)

    print("[2/4] Checking missing and duplicate values", flush=True)
    missing = {
        field: sum(not (row.get(field) or "").strip() for row in rows)
        for field in fields
    }
    article_ids = [(row.get("article_id") or "").strip() for row in rows]
    duplicate_ids = sum(count - 1 for count in Counter(article_ids).values() if count > 1)

    print("[3/4] Checking image-path matches", flush=True)
    matched = 0
    empty_images = 0
    for row in rows:
        relative = (row.get("image_path") or "").strip()
        if not relative:
            continue
        image_path = resolve_image_path(image_root, relative)
        if image_path.is_file():
            matched += 1
            if image_path.stat().st_size == 0:
                empty_images += 1
    match_rate = matched / len(rows) if rows else 0.0

    report = {
        "input_csv": str(input_csv),
        "image_root": str(image_root),
        "row_count": len(rows),
        "fields": fields,
        "missing_values": missing,
        "duplicate_article_ids": duplicate_ids,
        "matched_images": matched,
        "empty_images": empty_images,
        "image_match_rate": round(match_rate, 6),
        "unique_product_groups": len(
            {(row.get("product_group_name") or "").strip() for row in rows}
        ),
        "unique_product_types": len(
            {(row.get("product_type_name") or "").strip() for row in rows}
        ),
        "unique_colours": len(
            {(row.get("colour_group_name") or "").strip() for row in rows}
        ),
    }
    print(f"[4/4] Writing report: {args.report_path.resolve()}", flush=True)
    write_json(args.report_path.resolve(), report)
    print(
        f"SUCCESS: rows={len(rows):,}, duplicates={duplicate_ids}, "
        f"images={matched:,}/{len(rows):,} ({match_rate:.2%}), empty={empty_images}",
        flush=True,
    )
    if not rows or duplicate_ids or matched != len(rows) or empty_images:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
