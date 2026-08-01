# Java 后端统一入口

`java-backend` 是服装购买决策平台的 Java 业务入口，负责认证、购物车、订单和对 Python 服务的网关代理。

## 服务边界

- Java：用户认证、购物车、订单、JWT、PostgreSQL、Redis 缓存和运行指标。
- Python：RAG、模型调用、向量检索和商品推荐。
- Java 会将未由自身处理的 `/api/**` 与 `/media/**` 请求代理到 Python RAG 服务。

本模块不修改 `backend/` 下的 Python RAG 代码。

## 本地开发

本地默认启用 `local` Profile：Java 监听 `127.0.0.1:8080`，使用文件型 H2 数据库和进程内缓存，不需要启动 PostgreSQL 或 Redis。

先启动 Python 服务，再启动 Java 服务：

```powershell
cd D:\727push
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18000

cd D:\727push\java-backend
mvn spring-boot:run
```

常用检查地址：

```text
健康检查: http://127.0.0.1:8080/actuator/health
Prometheus 指标: http://127.0.0.1:8080/actuator/prometheus
Python 商品代理: http://127.0.0.1:8080/api/products?page=1&page_size=12&sort=popular
```

运行 Java 测试：

```powershell
cd D:\727push\java-backend
mvn test
```

## 核心接口

所有购物车和订单接口都要求：

```text
Authorization: Bearer <token>
```

认证接口：

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

购物车接口：

```text
POST   /api/cart/items
GET    /api/cart
PATCH  /api/cart/items/{itemId}
DELETE /api/cart/items/{itemId}
DELETE /api/cart
```

订单接口：

```text
POST /api/orders
GET  /api/orders
GET  /api/orders/{orderId}
POST /api/orders/{orderId}/cancel
```

创建订单时还必须提供 `Idempotency-Key` 请求头。同一个用户重复使用该键会得到同一笔订单，避免网络重试或重复点击造成重复下单。订单由已选中的购物车项生成，初始状态为 `PENDING_PAYMENT`。

## VMware Linux 部署

以下命令在 VMware 中的 Linux 虚拟机项目根目录执行。首次部署前必须设置强密码，`.env` 只保存于服务器，不应提交到 Git。

```bash
git pull --ff-only
cp .env.example .env
```

编辑 `.env`，至少替换以下三个示例值：

```text
AUTH_JWT_SECRET=
POSTGRES_PASSWORD=
REDIS_PASSWORD=
```

然后构建并启动全部服务：

```bash
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/actuator/health
curl --fail http://127.0.0.1:8080/actuator/prometheus | head
```

预期健康检查返回 `UP`，Prometheus 地址返回文本指标。生产环境自动启用 `prod` Profile，Java 使用 PostgreSQL 保存用户、购物车和订单数据；Redis 只缓存订单列表，失效或不可用时订单查询会自动回退到 PostgreSQL。

查看运行日志：

```bash
docker compose logs -f java-backend
docker compose logs -f postgres redis
```

停止服务但保留 PostgreSQL 数据：

```bash
docker compose down
```
