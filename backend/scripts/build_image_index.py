from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.image_encoder import DEFAULT_CLIP_MODEL, create_image_encoder
from data_utils import DEFAULT_CATALOG_DIR, resolve_catalog_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local product image index.")
    parser.add_argument(
        "--input_csv",
        type=Path,
        default=DEFAULT_CATALOG_DIR / "articles_sample.csv",
    )
    parser.add_argument(
        "--image_root",
        type=Path,
        default=None,
        help="Base directory for image_path values (default: input CSV directory).",
    )
    parser.add_argument(
        "--index_dir",
        type=Path,
        default=BACKEND_DIR / "data" / "vector_store" / "image",
    )
    parser.add_argument(
        "--backend",
        choices=("transformers-clip", "pixel"),
        default="transformers-clip",
    )
    parser.add_argument("--model", default=DEFAULT_CLIP_MODEL)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def read_products(path: Path, image_root: Path) -> tuple[list[dict[str, str]], list[Path]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    products: list[dict[str, str]] = []
    image_paths: list[Path] = []
    missing_images = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"article_id", "image_path"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError("Input CSV must contain article_id and image_path columns.")
        seen: set[str] = set()
        for row in reader:
            article_id = (row.get("article_id") or "").strip()
            relative = (row.get("image_path") or "").strip().replace("/", os.sep)
            image_path = (image_root / relative).resolve()
            if not image_path.is_relative_to(image_root):
                raise RuntimeError(f"Image path escapes --image_root: {relative}")
            if not article_id or article_id in seen:
                continue
            if not image_path.is_file():
                missing_images += 1
                continue
            row["article_id"] = article_id.zfill(10) if article_id.isdigit() else article_id
            products.append(row)
            image_paths.append(image_path)
            seen.add(article_id)
    if missing_images:
        print(f"      skipped missing images: {missing_images:,}", flush=True)
    if not products:
        raise RuntimeError("No products with readable image paths were found.")
    return products, image_paths


def encode_images(encoder, paths: list[Path], batch_size: int) -> np.ndarray:
    batches: list[np.ndarray] = []
    for start in range(0, len(paths), batch_size):
        batch_paths = paths[start : start + batch_size]
        images: list[Image.Image] = []
        try:
            for path in batch_paths:
                with Image.open(path) as source:
                    source.load()
                    images.append(source.convert("RGB"))
        except (OSError, UnidentifiedImageError) as error:
            raise RuntimeError(f"Cannot read product image: {path}") from error
        batches.append(encoder.encode(images, batch_size=batch_size))
        completed = min(start + len(batch_paths), len(paths))
        print(f"      encoded {completed:,}/{len(paths):,} images", flush=True)
    return np.concatenate(batches, axis=0)


def write_index(
    index_dir: Path,
    products: list[dict[str, str]],
    embeddings: np.ndarray,
    metadata: dict[str, object],
    force: bool,
) -> None:
    if index_dir.exists() and any(index_dir.iterdir()) and not force:
        raise RuntimeError(
            f"Index directory is not empty: {index_dir}. Use --force to replace it."
        )
    index_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".image_index_", dir=index_dir.parent))
    try:
        np.save(staging / "embeddings.npy", embeddings.astype(np.float32))
        with (staging / "products.jsonl").open("w", encoding="utf-8") as handle:
            for product in products:
                handle.write(json.dumps(product, ensure_ascii=False) + "\n")
        (staging / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for name in ("embeddings.npy", "products.jsonl", "metadata.json"):
            os.replace(staging / name, index_dir / name)
    finally:
        staging.rmdir()


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        raise ValueError("--batch_size must be greater than zero.")
    input_csv = resolve_catalog_csv(args.input_csv)
    image_root = (args.image_root or input_csv.parent).resolve()
    index_dir = args.index_dir.resolve()

    print(f"[1/4] Reading products: {input_csv}", flush=True)
    products, paths = read_products(input_csv, image_root)
    print(f"      products with images: {len(products):,}", flush=True)

    print(f"[2/4] Loading image encoder: {args.backend}", flush=True)
    encoder = create_image_encoder(args.backend, args.model, args.device)

    print("[3/4] Encoding product images", flush=True)
    embeddings = encode_images(encoder, paths, args.batch_size)
    if embeddings.shape != (len(products), encoder.dimension):
        raise RuntimeError(f"Unexpected embedding shape: {embeddings.shape}")

    metadata = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend,
        "model": args.model if args.backend == "transformers-clip" else "pixel-smoke-test",
        "dimension": encoder.dimension,
        "count": len(products),
        "input_csv": str(input_csv),
        "image_root": str(image_root),
    }
    print(f"[4/4] Writing image index: {index_dir}", flush=True)
    write_index(index_dir, products, embeddings, metadata, args.force)
    print(f"SUCCESS: indexed {len(products):,} product images", flush=True)
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
