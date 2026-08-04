# 天池商品数据导入说明

## 本地准备

请在遵守天池“淘宝服装搭配数据集”许可、下载资格和署名要求的前提下下载数据集。原始压缩包、解压后的元数据和图片只能放在受忽略的 `backend/data/raw/` 中。天池导入产物默认写入受忽略的 `backend/data/tianchi-catalog/`；不要把原始数据、图片、SQLite 数据库或文本索引提交到 Git。

先确认元数据文件、图片目录和真实字段名。CSV 使用第一条命令查看表头；JSON、JSONL 或 NDJSON 使用第二条命令查看首条记录。

```powershell
Get-Content "<metadata.csv>" -TotalCount 1
Get-Content "<metadata.json-or-jsonl>" -TotalCount 1
Get-ChildItem "<images-dir>" -File -Recurse | Measure-Object
```

元数据可以是 CSV、JSONL、NDJSON 或 JSON 对象数组。请把所有尖括号占位符替换为实际路径或字段名，尤其是商品 ID、名称和图片相对路径字段。最小导入命令只需要三个必填列：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_catalog.py `
  --metadata "<metadata-file>" `
  --images-dir "<images-dir>" `
  --id-column "<id-column>" `
  --name-column "<name-column>" `
  --image-column "<image-column>"
```

商品 ID 只能包含字母、数字、短横线和下划线。价格和热度如被提供，必须是大于等于零的有限数值。分类、颜色、描述、价格和热度列都是可选列，但一旦提供必须与源文件字段名完全一致：

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

默认导入 5,000 件商品，随机种子为 42；可用 `--sample-size` 和 `--seed` 调整。导入会跳过无效或重复图片、路径越界图片、非法商品 ID 和非法数值。若有效商品不足请求数量，原有运行目录不会被替换。导入途中被中断时，下次导入会先恢复未完成发布的旧目录。

## 构建本地运行数据

先生成 SQLite 文件并校验 CSV 与图片。文本索引不需要在本地上传或复制，Docker 构建后端镜像时会从 CSV 重新生成它。

```powershell
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py `
  --input_csv backend\data\tianchi-catalog\articles_sample.csv `
  --db_path backend\data\tianchi-catalog\app.db
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py `
  --input_csv backend\data\tianchi-catalog\articles_sample.csv `
  --image_root backend\data\tianchi-catalog `
  --report_path backend\data\tianchi-catalog\inspection_report.json
```

确认 `backend/data/tianchi-catalog/` 中存在且只准备发布以下四类文件：`articles_sample.csv`、`images/`、`catalog_manifest.json` 和 `app.db`。不要上传 `vector_store/text/`。

## 发布到 VMware 虚拟机

以下步骤假设虚拟机项目目录为 `/root/RAG-agent`。先从 Windows 把四类产物上传到新的发布目录，不能直接上传到正在运行的 `backend/data/sample/` 或 `backend/data/sqlite/`。

```powershell
$release = "tianchi-20260803-001"
ssh root@192.168.100.128 "mkdir -p /root/catalog-releases/$release"
scp backend\data\tianchi-catalog\articles_sample.csv root@192.168.100.128:/root/catalog-releases/$release/
scp backend\data\tianchi-catalog\catalog_manifest.json root@192.168.100.128:/root/catalog-releases/$release/
scp backend\data\tianchi-catalog\app.db root@192.168.100.128:/root/catalog-releases/$release/
scp -r backend\data\tianchi-catalog\images root@192.168.100.128:/root/catalog-releases/$release/
```

登录虚拟机后执行下面的发布脚本。它会停止 Python 后端、给当前后端镜像打回滚标签、把现有运行数据移动到带时间戳的仓库外备份目录、切换新数据、移走旧文本索引后构建镜像。构建、启动或健康检查失败时，脚本会恢复旧镜像和旧数据，再强制创建旧容器；成功后保留备份与回滚镜像标签，便于人工回退。

```bash
set -euo pipefail
cd /root/RAG-agent
release=/root/catalog-releases/tianchi-20260803-001
test -f "$release/articles_sample.csv"
test -d "$release/images"
test -f "$release/catalog_manifest.json"
test -f "$release/app.db"

backup_dir="/root/catalog-backups/tianchi-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir" backend/data/sample backend/data/sqlite
backend_container=$(docker compose ps -q backend)
test -n "$backend_container"
backend_image=$(docker inspect --format '{{.Image}}' "$backend_container")
backend_image_name=$(docker compose config --images backend)
rollback_image="${backend_image_name}:pre-tianchi-$(date -u +%Y%m%dT%H%M%SZ)"
docker tag "$backend_image" "$rollback_image"
docker compose stop backend

move_if_present() {
  source=$1
  target=$2
  if [ -e "$source" ] || [ -L "$source" ]; then
    mv "$source" "$target"
  fi
  return 0
}

rollback() {
  rollback_status=$?
  trap - ERR
  set +e
  rollback_failed=0
  docker compose stop backend || rollback_failed=1
  for item in images articles_sample.csv catalog_manifest.json; do
    target="backend/data/sample/$item"
    move_if_present "$target" "$backup_dir/failed-$item" || rollback_failed=1
    move_if_present "$backup_dir/$item" "$target" || rollback_failed=1
  done
  target=backend/data/sqlite/app.db
  move_if_present "$target" "$backup_dir/failed-app.db" || rollback_failed=1
  move_if_present "$backup_dir/app.db" "$target" || rollback_failed=1
  move_if_present "$backup_dir/text" backend/data/vector_store/text || rollback_failed=1
  docker tag "$rollback_image" "$backend_image_name" || rollback_failed=1
  docker compose up -d --force-recreate --no-deps --no-build backend || rollback_failed=1
  rollback_healthy=0
  for attempt in {1..12}; do
    if curl --fail --silent http://127.0.0.1:18000/health; then
      rollback_healthy=1
      break
    fi
    sleep 5
  done
  if [ "$rollback_healthy" -ne 1 ]; then rollback_failed=1; fi
  if [ "$rollback_failed" -ne 0 ]; then
    echo "回滚未完成，请检查 $backup_dir 中的备份和 Docker 日志。" >&2
    exit 2
  fi
  exit "$rollback_status"
}
trap rollback ERR

for item in images articles_sample.csv catalog_manifest.json; do
  target="backend/data/sample/$item"
  if [ -e "$target" ] || [ -L "$target" ]; then mv "$target" "$backup_dir/$item"; fi
done
if [ -e backend/data/sqlite/app.db ] || [ -L backend/data/sqlite/app.db ]; then
  mv backend/data/sqlite/app.db "$backup_dir/app.db"
fi
if [ -e backend/data/vector_store/text ] || [ -L backend/data/vector_store/text ]; then
  mkdir -p backend/data/vector_store
  mv backend/data/vector_store/text "$backup_dir/text"
fi

mv "$release/images" backend/data/sample/images
mv "$release/articles_sample.csv" backend/data/sample/articles_sample.csv
mv "$release/catalog_manifest.json" backend/data/sample/catalog_manifest.json
mv "$release/app.db" backend/data/sqlite/app.db

docker compose build backend
docker compose up -d backend
curl --fail http://127.0.0.1:18000/health
trap - ERR
```

发布后访问 `http://192.168.100.128:5173`，确认商品列表和图片可加载。四类运行数据只保留在虚拟机发布目录与备份目录，不应从该部署目录执行提交或推送。
