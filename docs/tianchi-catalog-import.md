# 天池商品数据导入说明

## 天池原始数据说明

请在遵守天池“淘宝服装搭配数据集”许可、下载资格和署名要求的前提下使用数据。天池原始文件放在 `backend/data/raw/tianchi/`，其中 `dim_items.txt` 是空格分隔的原始文本，图片文件在 `images/` 目录里，文件名通常就是商品 ID。

如果天池提供的是大型图片 ZIP，请用 `tar -xf` 解压，不要用 PowerShell 的 `Expand-Archive`，因为它对这类 ZIP 不兼容。解压后的文本、图片和后续导入产物都应保留在 Git 忽略目录中。

```powershell
tar -xf backend\data\raw\tianchi\archive\tianchi_fm_img3_1.zip -C backend\data\raw\tianchi\images
```

天池未提供原始售价，目录里的价格只是给购物车和订单流程使用的确定性演示价格，不代表原始商品价格。

## 导入命令

运行下面的 PowerShell 命令，把 `dim_items.txt` 和图片目录导入为本地商品目录：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_fashion_collection.py `
  --items backend\data\raw\tianchi\dim_items.txt `
  --images-dir backend\data\raw\tianchi\images `
  --sample-size 5000 `
  --seed 42
```

默认导入结果写入受 Git 忽略的 `backend/data/tianchi-catalog/`。导入过程中会跳过无效记录、缺失图片、重复图片、路径越界图片和非法数值；如果有效商品不足，原有运行目录不会被替换。

## 通用格式导入（可选）

如果后续取得包含可读商品名和价格的天池元数据，可继续使用通用导入器。元数据支持 CSV、JSONL、NDJSON 或 JSON 对象数组；商品 ID、名称和图片相对路径字段是必填项：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_catalog.py `
  --metadata "<metadata-file>" `
  --images-dir "<images-dir>" `
  --id-column "<id-column>" `
  --name-column "<name-column>" `
  --image-column "<image-column>"
```

## 本地准备与边界

导入前先确认原始文本、图片目录和实际字段名。`dim_items.txt` 的内容用于原始商品 ID 和类目 ID；导入器会把它转换成现有商品目录所需的展示字段。这个流程只负责数据落地，不改动 Python RAG 服务，也不要求把原始天池数据、图片、SQLite 数据库或生成目录提交到 Git。

```powershell
Get-Content backend\data\raw\tianchi\dim_items.txt -TotalCount 3
Get-ChildItem backend\data\raw\tianchi\images -File -Recurse | Measure-Object
```

## 构建本地运行数据

导入完成后，生成 SQLite 文件并校验 CSV 与图片。文本索引不需要在本地上传或复制，Docker 构建后端镜像时会从 CSV 重新生成它。

```powershell
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py `
  --input_csv backend\data\tianchi-catalog\articles_sample.csv `
  --db_path backend\data\tianchi-catalog\app.db
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py `
  --input_csv backend\data\tianchi-catalog\articles_sample.csv `
  --image_root backend\data\tianchi-catalog `
  --report_path backend\data\tianchi-catalog\inspection_report.json
```

确认 `backend/data/tianchi-catalog/` 中只准备发布以下四类文件：`articles_sample.csv`、`images/`、`catalog_manifest.json` 和 `app.db`。不要上传 `vector_store/text/`，也不要提交原始压缩包和中间产物。

## 发布到 VMware 虚拟机

以下步骤假设虚拟机项目目录为 `/root/RAG-agent`。先从 Windows 把四类产物上传到新的发布目录，不能直接上传到正在运行的 `backend/data/sample/` 或 `backend/data/sqlite/`。

```powershell
$release = "tianchi-20260804-001"
ssh root@192.168.100.128 "mkdir -p /root/catalog-releases/$release"
scp backend\data\tianchi-catalog\articles_sample.csv root@192.168.100.128:/root/catalog-releases/$release/
scp backend\data\tianchi-catalog\catalog_manifest.json root@192.168.100.128:/root/catalog-releases/$release/
scp backend\data\tianchi-catalog\app.db root@192.168.100.128:/root/catalog-releases/$release/
scp -r backend\data\tianchi-catalog\images root@192.168.100.128:/root/catalog-releases/$release/
```

登录虚拟机后，按既有发布流程切换这四类运行数据并重建后端镜像。发布前应先为当前数据和后端镜像保留可回滚备份；构建、启动或健康检查失败时恢复旧数据和旧镜像。发布成功后访问 `http://192.168.100.128:5173`，确认商品列表和图片均可加载。
