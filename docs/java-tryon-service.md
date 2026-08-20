# Java 高并发虚拟试穿

虚拟试穿的对外 API、并发调度和任务状态都由 `java-backend` 负责；Python 后端仅暴露 Docker 内部可访问的推理桥接接口。

```text
Browser -> Java API -> PostgreSQL (job state) -> Redis Stream -> bounded Java Worker Pool -> Python private inference -> provider
                                  ^                    |                         |
                                  |                    +-- consumer group        +-- only synthetic body profile
                                  +-- idempotency / retry / recovery
```

实现要点：

- `virtual_try_on_jobs` 是权威状态机：`QUEUED -> PROCESSING -> SUCCEEDED | FAILED`；结果到期进入终态 `EXPIRED`，失败重试回到 `QUEUED`。
- 每次状态变化都会写入 `virtual_try_on_job_events`，可通过 `GET /api/try-on/jobs/{id}/events` 按时间查看任务轨迹。
- `POST /api/try-on/jobs` 要求 `Idempotency-Key`。PostgreSQL 唯一约束保证同一用户重放请求只创建一条任务。
- Redis Stream consumer group 负责跨实例分发；Worker Pool 由 `TRYON_WORKER_COUNT` 和 `TRYON_QUEUE_CAPACITY` 严格限界。处理中实例异常时，超过 `TRYON_PROCESSING_LEASE` 的任务会被回收并重试。
- Redis Lua 固定窗口实现每用户限流。结果图存入 Redis 并使用 TTL 清理；生产中若结果量大，应将 `TryOnResultStore` 换成私有对象存储实现。
- 成功结果和分享都返回 15 分钟 HMAC 签名 URL。图片读取不依赖浏览器携带鉴权头，签名绑定任务、用户和结果键。
- Java 通过 `X-Agent-Internal-Token` 调用 Python 的 `/internal/try-on/render`；该路径不经网关对外暴露。

主要配置：

```env
TRYON_WORKER_COUNT=4
TRYON_QUEUE_CAPACITY=128
TRYON_MAX_ATTEMPTS=3
TRYON_RATE_LIMIT_COUNT=10
TRYON_RATE_LIMIT_WINDOW=10m
TRYON_PROVIDER_TIMEOUT=90s
TRYON_PROCESSING_LEASE=2m
TRYON_EXPIRY_INTERVAL_MS=60000
VTO_RESULT_SIGNING_SECRET=replace-with-a-random-secret
AGENT_INTERNAL_TOKEN=replace-with-a-random-internal-token
```
