# RAG-agent

AI 服装购买决策平台。项目采用 Java 与 Python 分工协作：Java 承担业务系统和高并发入口，Python 承担 RAG、模型调用、向量检索和推荐能力。

## 服务组成

| 服务 | 默认端口 | 职责 |
| --- | --- | --- |
| frontend | 5173 | 用户界面 |
| java-backend | 8080 | 认证、购物车、订单、网关、指标 |
| backend | 18000 | Python RAG、商品推荐、模型能力 |
| postgres | 内部服务 | Java 业务数据持久化 |
| redis | 内部服务 | Java 订单列表缓存 |

Java 会把仍由 Python 负责的 `/api/**` 和 `/media/**` 请求代理到 Python 服务。`backend/` 的 Python RAG 代码由对应负责人维护，本仓库的 Java 生产化改造不改动它。

## 本地启动

开发 Java 功能时可分别启动 Python 和 Java：

```powershell
cd D:\727push
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18000

cd D:\727push\java-backend
mvn spring-boot:run
```

Java 本地默认使用 H2 和进程内缓存，健康检查为 `http://127.0.0.1:8080/actuator/health`。

## VMware Linux 部署

在 Linux 虚拟机的项目根目录执行：

```bash
git pull --ff-only
cp .env.example .env
```

编辑 `.env`，将 `AUTH_JWT_SECRET`、`AGENT_INTERNAL_TOKEN`、`POSTGRES_PASSWORD` 和 `REDIS_PASSWORD` 改为强随机值。不要提交 `.env`。

```bash
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/actuator/health
curl --fail http://127.0.0.1:8080/actuator/prometheus | head
```

详情见 [Java 后端部署说明](java-backend/README.md)。

天池真实商品数据、图片和生成运行数据不能提交到 Git；导入与仅重建 Python 后端的步骤见[天池商品数据导入说明](docs/tianchi-catalog-import.md)。

已有 H2 数据的环境请先阅读其中的“从旧 H2 Compose 升级”章节；本次 PostgreSQL 切换不会自动迁移旧数据。
