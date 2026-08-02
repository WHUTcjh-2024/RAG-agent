# 第一阶段生产化改造设计

## 目标

在不改变现有 Java 用户、购物车和订单业务行为的前提下，为 Java 服务建立可在 Linux 虚拟机上运行的基础部署环境。第一阶段交付 PostgreSQL、Redis、Docker Compose、运行指标和中文部署说明。

本地 IDEA 开发与现有 Maven 测试继续默认使用 H2，不要求开发者先启动 Docker。

## 范围

本期包含：

- 新增 `local` 与 `prod` Spring Profile。
- `local` 保留现有 H2 配置；`prod` 使用 PostgreSQL。
- 使用环境变量配置数据库、Redis、RAG 上游地址和 JWT 密钥。
- 新增 Redis 连接配置与一个可验证的缓存能力。
- 在现有根目录 `docker-compose.yml` 中保留 `backend` 与 `frontend` 服务定义不变，仅为 Java 服务补充 PostgreSQL、Redis 和生产配置。
- 通过 Actuator 暴露 `health`、`info`、`prometheus` 指标端点。
- 新增 Compose 启动验证及配置加载测试。
- 更新中文部署文档与 `.env.example`，不提交真实密码。

本期不包含：

- Kafka、RabbitMQ、分布式事务或异步下单。
- 真实支付对接。
- 数据库读写分离、分库分表或多节点 Redis。
- 修改 Python RAG 代码、依赖、接口或现有 `backend` Compose 服务定义。Java 继续通过 `RAG_UPSTREAM_BASE_URL` 访问现有 Python 服务。
- 将订单写操作放入缓存。订单、购物车和用户数据仍以 PostgreSQL 为唯一事实来源。

## 运行架构

```text
浏览器 / 前端
       |
       v
Java Gateway (8080, Spring Boot)
  |            |              |
  |            |              +-- HTTP --> Python RAG（现有 Compose 的 backend 服务）
  |            +-- Redis（缓存与后续限流基础）
  +-- PostgreSQL（用户、购物车、订单）
```

现有 Docker Compose 继续管理 Python RAG、Java 和前端；本期仅新增 PostgreSQL 与 Redis 并调整 Java 服务环境变量。PostgreSQL 和 Redis 仅暴露给 Compose 内部网络；Java 的 8080 端口映射至虚拟机，以便前端和运维检查访问。

## 配置设计

### Local Profile

- 默认 Profile 为 `local`。
- 保持现有文件型 H2、Flyway 和本地 RAG 地址。
- Maven 集成测试继续使用 H2，保证开发和 CI 不依赖 Docker。

### Prod Profile

- `SPRING_DATASOURCE_URL`、`SPRING_DATASOURCE_USERNAME`、`SPRING_DATASOURCE_PASSWORD` 指向 PostgreSQL。
- `SPRING_DATA_REDIS_HOST`、`SPRING_DATA_REDIS_PORT`、`SPRING_DATA_REDIS_PASSWORD` 指向 Redis。
- `AUTH_JWT_SECRET`、数据库密码和 Redis 密码必须由虚拟机 `.env` 或部署系统注入，禁止写入 Git。
- Compose 中的 `RAG_UPSTREAM_BASE_URL` 继续使用 `http://backend:18000`。本期不改动 Python 服务本身。
- PostgreSQL 使用 Flyway 执行已有迁移，`ddl-auto` 继续为 `validate`，不允许生产环境由 Hibernate 自动改表。

## Redis 使用边界

第一期只引入低风险的只读缓存：缓存当前用户的订单列表查询，使用用户 ID 作为缓存键前缀，并在创建或取消订单后删除该用户的订单列表缓存。

缓存不可用时，订单查询必须降级为直接查询 PostgreSQL，不能影响下单、取消订单或登录。Redis 不存储密码、JWT 明文或订单唯一事实数据。

## 可观测性与健康检查

- `GET /actuator/health`：供 Docker 健康检查和部署平台探测。
- `GET /actuator/info`：展示不含敏感信息的应用信息。
- `GET /actuator/prometheus`：供 Prometheus 抓取 JVM、HTTP、连接池等基础指标。
- Docker Compose 中为 Java、PostgreSQL、Redis 配置健康检查；Java 在数据库与 Redis就绪后启动。

暴露的管理端点不应包含 `env`、`configprops` 或敏感配置。

## 错误处理

- 缺少必要生产环境变量时，服务在启动阶段失败，避免以不安全默认密码运行。
- 数据库不可用时，健康检查报告不健康，业务请求按现有统一错误机制返回失败。
- Redis 不可用时，健康检查会反映依赖状态；只读缓存调用应捕获缓存异常并回退数据库查询。
- Flyway 迁移失败时，应用不得继续对外提供业务服务。

## 验证

1. `mvn test`：验证现有业务和新增缓存失效逻辑，使用 H2。
2. `docker compose config`：验证 Compose 与环境变量文件语法。
3. 在 Ubuntu 虚拟机执行 `docker compose up -d --build`，确认现有 Python RAG、Java、前端服务以及新增 PostgreSQL、Redis 均可启动。
4. 使用虚拟机 IP 地址访问 `http://虚拟机IP:8080/actuator/health`，确认返回健康状态。
5. 使用登录、购物车、创建订单、查询订单流程验证 PostgreSQL 数据落库；重复查询验证 Redis 缓存可用；停止 Redis 后验证订单查询仍可回退数据库。

## 成功标准

- 不修改 Python RAG 主流程。
- 本地 H2 测试持续通过。
- Ubuntu 虚拟机中可使用一条 Compose 命令启动 Java、PostgreSQL、Redis。
- Java 服务使用 PostgreSQL 成功完成现有用户、购物车、订单流程。
- 不提交任何生产密码、JWT 密钥或私有地址。
- Prometheus 格式指标和健康检查端点可访问。
