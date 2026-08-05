# 图片索引生产部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为生产部署提供可选、持久化的商品图片索引构建能力。

**Architecture:** Dockerfile 使用 `BUILD_IMAGE_INDEX` 控制是否调用现有索引脚本。Compose 将开关从 `.env` 传入构建，为运行容器指定 `/app/data/vector_store/image`，并用固定的 `rag-agent-backend` 镜像名作为生产回退契约。

**Tech Stack:** Dockerfile、Docker Compose、Python CLIP 索引脚本、pytest。

## Global Constraints

- 不修改 `backend/app/` 的 Python RAG 业务逻辑或 API。
- 不提交天池图片、CSV、SQLite 数据库或生成索引。
- `BUILD_IMAGE_INDEX` 默认值为 `0`。
- backend 镜像默认名固定为 `rag-agent-backend`；图片索引构建前的备份和回退只能使用这一稳定标签，不依赖 Compose 自动生成的镜像名。
- 生产索引使用 CPU 和 `--batch_size 8`。

---

### Task 1: 增加可选图片索引镜像构建

**Files:**
- Modify: `backend/Dockerfile:1-10`
- Test: Docker build with `BUILD_IMAGE_INDEX=0`

**Interfaces:**
- Consumes: `backend/scripts/build_image_index.py` 的现有 CLI。
- Produces: 开关为 `1` 时，在 `/app/data/vector_store/image/` 写入 `embeddings.npy`、`products.jsonl`、`metadata.json`。

- [ ] **Step 1: 验证默认构建基线**

```powershell
docker build --build-arg BUILD_IMAGE_INDEX=0 -t rag-agent-backend:index-off backend
```

Expected: 构建成功，日志不出现 `Loading image encoder`。

- [ ] **Step 2: 修改 Dockerfile**

在 `COPY data ./data` 前声明：

```dockerfile
ARG BUILD_IMAGE_INDEX=0
```

在现有文本索引构建命令后增加：

```dockerfile
RUN if [ "$BUILD_IMAGE_INDEX" = "1" ]; then \
      python scripts/build_image_index.py \
        --input_csv data/sample/articles_sample.csv \
        --index_dir data/vector_store/image \
        --backend transformers-clip \
        --device cpu \
        --batch_size 8; \
    fi
```

- [ ] **Step 3: 验证默认构建并提交**

```powershell
docker build --build-arg BUILD_IMAGE_INDEX=0 -t rag-agent-backend:index-off backend
git add backend/Dockerfile
git commit -m "feat: 支持可选图片索引镜像构建"
```

Expected: Docker 命令 exit code `0`，提交只包含 Dockerfile。

### Task 2: 接入 Compose 构建开关与运行时路径

**Files:**
- Modify: `docker-compose.yml:2-11`
- Modify: `.env.example:1-8`
- Test: `docker compose --env-file .env.example config --quiet`

**Interfaces:**
- Consumes: `.env` 的 `BUILD_IMAGE_INDEX`，缺失时使用 `0`。
- Produces: 后端构建参数、`IMAGE_INDEX_DIR=/app/data/vector_store/image` 和固定为 `rag-agent-backend` 的镜像标签回退契约。

- [ ] **Step 1: 写入 Compose 配置**

将：

```yaml
build: ./backend
```

替换为：

```yaml
build:
  context: ./backend
  args:
    BUILD_IMAGE_INDEX: ${BUILD_IMAGE_INDEX:-0}
image: ${BACKEND_IMAGE:-rag-agent-backend}
```

并在 `backend.environment` 中添加：

```yaml
IMAGE_INDEX_DIR: /app/data/vector_store/image
```

在 `.env.example` 索引配置区加入：

```dotenv
# backend 镜像固定名称，供图片索引构建前的备份与回退使用。
BACKEND_IMAGE=rag-agent-backend
# 生产镜像构建时设为 1，生成 CLIP 商品图片索引；日常开发和 CI 保持 0。
BUILD_IMAGE_INDEX=0
```

- [ ] **Step 2: 验证默认值和启用值**

```powershell
docker compose --env-file .env.example config --quiet
$env:BUILD_IMAGE_INDEX = "1"
docker compose --env-file .env.example config | Select-String "BUILD_IMAGE_INDEX|IMAGE_INDEX_DIR"
Remove-Item Env:BUILD_IMAGE_INDEX
```

Expected: 两次解析均成功；启用值为 `1`，路径为 `/app/data/vector_store/image`。

- [ ] **Step 3: 提交配置**

```powershell
git add docker-compose.yml .env.example
git commit -m "feat: 配置生产图片索引路径"
```

### Task 3: 补充部署文档并回归验证

**Files:**
- Modify: `README.md` 的 VMware Linux 部署章节
- Test: `backend/tests`

**Interfaces:**
- Consumes: `.env` 的 `BUILD_IMAGE_INDEX=1`。
- Produces: 可复制的构建、健康检查与镜像回退步骤；其中 `rag-agent-backend` 是 Compose 固定的回退镜像名。

- [ ] **Step 1: 在 README 添加生产操作说明**

在 `docker compose up -d --build` 前增加：

```bash
# 首次生成图片索引时设置；兼容已有但缺少该变量的 .env。
if grep -q '^BUILD_IMAGE_INDEX=' .env; then
  sed -i 's/^BUILD_IMAGE_INDEX=.*/BUILD_IMAGE_INDEX=1/' .env
else
  echo 'BUILD_IMAGE_INDEX=1' >> .env
fi
docker image tag rag-agent-backend rag-agent-backend:before-image-index
docker compose build backend
docker compose up -d backend
curl --fail http://127.0.0.1:18000/health
```

`rag-agent-backend` 由 Compose 的 `image` 配置固定，是上述备份和下述回退命令的契约名称。要求确认响应中的 `image_index` 为 `true`。回退命令为：

```bash
docker image tag rag-agent-backend:before-image-index rag-agent-backend
docker compose up -d --no-build backend
```

- [ ] **Step 2: 运行回归验证并提交**

```powershell
& D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
git diff --check
docker compose --env-file .env.example config --quiet
git add README.md
git commit -m "docs: 补充图片索引生产部署说明"
```

Expected: Python 测试无失败，格式和 Compose 检查成功。

### Task 4: 创建中文 PR 并部署验证

**Files:**
- No source-file changes.

**Interfaces:**
- Consumes: 合并后的配置及虚拟机 `/root/RAG-agent` 中现有的天池数据。
- Produces: 健康响应中 `image_index: true`。

- [ ] **Step 1: 推送分支**

```powershell
git push -u origin feature/image-index-production
```

PR 标题：`feat: 支持生产环境图片索引构建`

- [ ] **Step 2: 合并后在虚拟机执行 README 的构建步骤**

部署前保留旧镜像标签，构建失败不替换正在运行的容器。

- [ ] **Step 3: 验证生产结果**

```bash
docker compose ps
curl -s http://127.0.0.1:18000/health
docker compose exec backend sh -lc 'test -f /app/data/vector_store/image/embeddings.npy'
```

Expected: 后端运行，`image_index` 为 `true`，索引文件存在。
