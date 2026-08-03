# 天池商品数据导入说明

## 准备数据

请在遵守天池“淘宝服装搭配数据集”许可、下载资格和署名要求的前提下下载数据集，并将原始压缩包、解压后的元数据和图片放到受忽略的 `backend/data/raw/`。原始包、商品图片、SQLite 数据库和文本索引都是运行数据，均不得提交到 Git。

先查看本地文件，确认元数据文件、图片目录和真实字段名：

```powershell
Get-ChildItem backend\data\raw -Recurse -File
```

元数据可以是 CSV、JSONL、NDJSON 或 JSON 对象数组。导入前请根据实际文件替换下面命令中的所有占位符，尤其是 ID、名称和图片相对路径字段名：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_catalog.py `
  --metadata "<metadata-file>" `
  --images-dir "<images-dir>" `
  --id-column "<id-column>" `
  --name-column "<name-column>" `
  --image-column "<image-column>" `
  --category-column "<category-column>" `
  --color-column "<color-column>" `
  --description-column "<description-column>" `
  --price-column "<price-column>" `
  --popularity-column "<popularity-column>"
```

默认导入 5,000 件商品，随机种子为 42。也可以用 `--sample-size` 和 `--seed` 显式调整。若必填字段缺失、图片缺失或损坏，或者有效商品不足 5,000 件，导入会失败并保留原有输出目录。

## 构建运行数据

导入完成后，依次构建 SQLite 商品库和文本索引，并检查结果：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py
backend\.venv\Scripts\python.exe backend\scripts\build_text_index.py --backend hashing --force
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py
```

## 部署到虚拟机

将以下五类运行数据上传到虚拟机相应的 `backend/data/` 目录：`articles_sample.csv`、`images/`、`catalog_manifest.json`、`app.db` 和 `vector_store/text/`。这些文件不进入 Git。

上传后只重建并重启 `backend` 服务：

```bash
cd /root/RAG-agent
docker compose build backend
docker compose up -d backend
curl --fail 'http://127.0.0.1:8080/api/products?page=1&page_size=1'
```

最后访问 `http://192.168.100.128:5173`，确认商品图片能够加载。
