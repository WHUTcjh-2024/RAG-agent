# Agent 生产运行时与面试证据

## 设计目标

在线商品检索、尺码决策和购物车确认保持同步 SSE；虚拟试穿、索引构建等慢任务仍由 Redis 队列和独立 Worker 承担。这样避免将所有请求无差别排队，保证搜索首 token 与决策响应的体验。

| 运行时能力 | 开发/单机 | 生产/多副本 | 不变量 |
| --- | --- | --- | --- |
| LangGraph checkpoint | SQLite | Postgres `PostgresSaver` | 相同 `task_id` 可恢复；状态不依赖 Pod 本地磁盘 |
| 重复执行协调 | 进程内锁 | Redis 带续租 lease | lease 只抑制重复执行，数据库幂等记录才是最终防线 |
| 会话与任务控制 | SQLite | Postgres | 取消、完成和会话删除必须跨副本可见 |
| Trace | 本地脱敏缓冲 + 日志 | OTLP Collector → Tempo/Jaeger | 不采集 prompt、图片路径、检索正文或用户 ID |
| Metrics | `/metrics` | Prometheus → Grafana | 仅低基数标签：node、outcome |
| 慢任务 | Redis worker | Redis worker，可水平扩容 | 任务有幂等键、重试、超时、限流和死信策略 |

## 生产配置

```dotenv
# API 运行时：两个及以上 backend 副本共享这两项基础设施。
AGENT_CHECKPOINT_BACKEND=postgres
AGENT_CHECKPOINT_DATABASE_URL=postgresql://atelier:password@postgres:5432/atelier?sslmode=disable
AGENT_CHECKPOINT_AUTO_SETUP=false
AGENT_MEMORY_BACKEND=postgres
AGENT_MEMORY_DATABASE_URL=postgresql://atelier:password@postgres:5432/atelier?sslmode=disable
AGENT_MEMORY_AUTO_SETUP=false
AGENT_TASK_LOCK_BACKEND=redis
AGENT_REDIS_URL=redis://:password@redis:6379/2
AGENT_TASK_LOCK_PREFIX=atelier:agent:task-lock
AGENT_TASK_LOCK_TTL_SECONDS=90
AGENT_TASK_LOCK_ACQUIRE_TIMEOUT_SECONDS=3

# 由 OTel Collector 接收；默认关闭时仍保留本地脱敏诊断。
OTEL_SERVICE_NAME=atelier-agent-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

部署前由一次性 migration Job 执行 `python scripts/setup_catalog.py`、`python scripts/build_catalog.py`、`python scripts/setup_agent_memory.py` 和 `python scripts/setup_agent_checkpoint.py`；运行时不自动建表。商品目录、Agent 会话与 checkpoint 现在全部使用 PostgreSQL，不再依赖 SQLite（`build_sqlite.py` 已移除）。LangGraph 官方将 SQLite 定位为本地/实验场景，并提供 `PostgresSaver` 作为生产数据库 checkpointer。[LangGraph persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence)

Postgres checkpoint 和 Agent 会话数据分别由单一 CronJob/数据库 scheduler 清理，而不是由每个 API 副本在请求路径上扫表。部署任务可调用 `python scripts/prune_agent_checkpoints.py`（Postgres checkpoint）及 `python scripts/prune_agent_memory.py`（Postgres 会话）；checkpoint 的生产清理应执行下面 SQL。部署时根据实际 LangGraph 版本校验表名和迁移版本：

```sql
DELETE FROM checkpoint_writes
WHERE thread_id IN (
  SELECT thread_id FROM checkpoints
  GROUP BY thread_id
  HAVING max((checkpoint->>'ts')::timestamptz) < now() - interval '24 hours'
);
DELETE FROM checkpoints
WHERE thread_id IN (
  SELECT thread_id FROM checkpoints
  GROUP BY thread_id
  HAVING max((checkpoint->>'ts')::timestamptz) < now() - interval '24 hours'
);
DELETE FROM checkpoint_blobs
WHERE thread_id NOT IN (SELECT DISTINCT thread_id FROM checkpoints);

DELETE FROM agent_sessions
WHERE updated_at < now() - interval '7 days';
DELETE FROM agent_task_controls
WHERE updated_at < now() - interval '7 days';
DELETE FROM agent_task_commits
WHERE session_id NOT IN (SELECT session_id FROM agent_sessions);
DELETE FROM agent_actions
WHERE expires_at < now() - interval '1 day';
```

## SLI、限额与告警

| SLI / guardrail | 初始目标 | 触发动作 |
| --- | ---: | --- |
| `agent_task_duration_seconds` P95 | < 3 s（非试穿） | 分解 node latency，限制 rerank / LLM 并发 |
| `agent_task_total{outcome="error"}` | < 1% | 按错误码、上游和模型版本回溯 trace |
| `agent_task_lease_contended_total` | < 0.5% | 排查客户端重试或 task ID 复用 |
| `agent_task_lease_lost_total` | 0 | 降级流量，排查 Redis 网络与 GC 停顿 |
| Redis worker backlog | < 60 s | HPA 扩 worker；超过阈值拒绝新试穿 |
| 每用户 LLM/试穿预算 | 配置化 | 429 + 明确的 retry-after，不静默降级为付费调用 |

压力验证至少覆盖：两个 API 副本对同一 `task_id` 并发请求只执行一次；执行中杀掉一个副本后另一个副本从 Postgres checkpoint 恢复；Redis 不可用时生产实例 fail-fast；同一确认动作重复提交不重复加购。

## 面试表达

> 我把 Agent 当作有状态、可恢复的交易协作服务，而不是一次 LLM 调用。在线链路用 Postgres checkpoint 保证故障恢复，用 Redis lease 抑制跨副本重复执行，并以数据库幂等记录兜底；通过 OTLP 和 Prometheus 定义 SLI。高耗时试穿走独立队列，检索与决策保持 SSE，同步链路不会被慢任务拖垮。

不要声称已经承载过真实百万流量。正确表述是：**完成了面向多副本生产部署的运行时设计与自动化验证，线上容量目标需要在目标集群和真实模型供应商条件下压测校准。**
