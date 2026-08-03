# 天池商品数据导入说明

## 准备数据

请在遵守天池“淘宝服装搭配数据集”许可、下载资格和署名要求的前提下下载数据集，并将原始压缩包、解压后的元数据和图片放到受忽略的 `backend/data/raw/`。原始包、商品图片、SQLite 数据库和文本索引都是运行数据，均不得提交到 Git。

先查看本地文件，确认元数据文件、图片目录和真实字段名：

```powershell
Get-ChildItem backend\data\raw -Recurse -File
```

元数据可以是 CSV、JSONL、NDJSON 或 JSON 对象数组。导入前请根据实际文件替换下面命令中的所有占位符，尤其是 ID、名称和图片相对路径字段名。最小有效命令只需要三个必填列：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_catalog.py `
  --metadata "<metadata-file>" `
  --images-dir "<images-dir>" `
  --id-column "<id-column>" `
  --name-column "<name-column>" `
  --image-column "<image-column>"
```

如果元数据包含分类、颜色、描述、价格或热度，可以额外指定对应字段；这些参数都是可选的，但一旦提供就必须与真实字段名完全一致：

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
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py --input_csv backend/data/sample/articles_sample.csv
backend\.venv\Scripts\python.exe backend\scripts\build_text_index.py --backend hashing --force
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py
```

## 部署到虚拟机

将以下四类运行数据上传到虚拟机相应的 `backend/data/` 目录：`articles_sample.csv`、`images/`、`catalog_manifest.json` 和 `app.db`。这些文件不进入 Git。不要上传 `vector_store/text/`：Dockerfile 会在重建 backend 镜像时生成文本索引，预先存在的索引会导致构建失败。

在重建 `backend` 前，先将虚拟机上已有的文本索引移到仓库外、带时间戳的备份目录。不要上传 `vector_store/text/`；Dockerfile 会在构建镜像时重新生成索引。

```bash
set -eu
cd /root/RAG-agent
index_dir=backend/data/vector_store/text
if [ -e "$index_dir" ] || [ -L "$index_dir" ]; then
  backup_dir="/root/catalog-backups/text-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p /root/catalog-backups
  test ! -e "$backup_dir"
  mv "$index_dir" "$backup_dir"
fi
docker compose build backend
docker compose up -d backend
curl --fail 'http://127.0.0.1:8080/api/products?page=1&page_size=1'
```

最后访问 `http://192.168.100.128:5173`，确认商品图片能够加载。
