FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
ARG BUILD_IMAGE_INDEX=0
ARG CATALOG_DIR=data/tianchi-catalog
COPY data ./data
RUN set -eu; \
    catalog_csv="${CATALOG_DIR}/articles_sample.csv"; \
    if [ ! -f "$catalog_csv" ]; then catalog_csv="data/tianchi-demo/articles_sample.csv"; fi; \
    python scripts/build_text_index.py --input_csv "$catalog_csv" --index_dir data/vector_store/text --backend hashing; \
    python scripts/build_sqlite.py --input_csv "$catalog_csv" --db_path data/sqlite/app.db; \
    if [ "$BUILD_IMAGE_INDEX" = "1" ]; then \
      python scripts/build_image_index.py \
        --input_csv "$catalog_csv" \
        --index_dir data/vector_store/image \
        --backend transformers-clip \
        --device cpu \
        --batch_size 8; \
    fi
EXPOSE 18000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18000"]
