FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
ARG BUILD_IMAGE_INDEX=0
COPY data ./data
RUN python scripts/build_text_index.py --input_csv data/sample/articles_sample.csv --index_dir data/vector_store/text --backend hashing
RUN if [ "$BUILD_IMAGE_INDEX" = "1" ]; then \
      python scripts/build_image_index.py \
        --input_csv data/sample/articles_sample.csv \
        --index_dir data/vector_store/image \
        --backend transformers-clip \
        --device cpu \
        --batch_size 8; \
    fi
EXPOSE 18000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18000"]
