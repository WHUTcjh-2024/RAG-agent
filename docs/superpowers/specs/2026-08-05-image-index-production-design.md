# 图片索引生产部署设计

## 目标

为天池服装商品生成可持久化的图片向量索引，使后端能启用视觉相似检索，并让健康检查中的 `image_index` 变为可用。

## 范围

- 仅调整后端镜像构建和 Docker Compose 运行配置。
- 索引输入为现有 `backend/data/sample/articles_sample.csv` 与对应图片目录。
- 使用现有 `build_image_index.py`、`openai/clip-vit-base-patch32` 和 CPU 编码器。
- 不修改 Python RAG 的接口、业务流程或天池原始数据。
- 不提交商品图片、SQLite 数据库或生成的索引文件。

## 方案

后端 Dockerfile 新增构建参数 `BUILD_IMAGE_INDEX`，默认值为 `0`。默认构建不生成图片索引，保证开发和 CI 不下载视觉模型。生产部署在 `.env` 中显式设置为 `1` 后，镜像构建将使用批量大小 `8` 生成 `data/vector_store/image` 索引。

Docker Compose 为后端设置：

```text
IMAGE_INDEX_DIR=/app/data/vector_store/image
```

这样运行中的后端读取的目录与索引脚本写入目录保持一致。索引随镜像层保存，普通容器重启不会丢失；重新构建生产镜像时会基于当前商品数据重新生成。

## 资源与运行方式

- 目标环境为 2 核 CPU、约 8GB 内存的 CentOS 虚拟机。
- 图片索引构建只使用 CPU，并使用 `--batch_size 8` 降低内存峰值。
- 首次生产构建需要下载 CLIP 模型，耗时取决于网络和 CPU 性能。
- 构建失败不会替换正在运行的后端容器；部署前应保留当前镜像标签作为回退点。

## 验证

1. 默认 Docker 构建不生成图片索引，保持 CI 与开发构建轻量。
2. 开启 `BUILD_IMAGE_INDEX=1` 的生产构建生成 `embeddings.npy`、`products.jsonl` 和 `metadata.json`。
3. 后端环境变量指向 `/app/data/vector_store/image`。
4. 现有 Python 测试继续通过。
5. 在虚拟机部署后，`/health` 返回的 `image_index` 为 `true`，并且前端商品页面仍可访问。

## 回退

如果生产镜像构建或启动失败，使用部署前保存的后端镜像标签重新启动 `backend` 服务。天池 CSV、图片和 SQLite 数据不在本次改动中迁移或覆盖。
