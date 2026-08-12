# AI 服装购买决策平台

## Agent Harness

项目将 Agent 的 Skill、工作流、工具权限、业务事实校验、确认式写入、Trace、回放和自动化评测收束为垂直领域 Harness。详见 [Agent Harness 说明](docs/agent-harness.md)。

项目默认使用天池服装目录。原始数据不进入仓库，先按[天池数据导入说明](docs/tianchi-catalog-import.md)生成 `backend/data/tianchi-catalog/`，再构建 SQLite 与检索索引。

运行时保留 `SQLITE_PATH`、`--sample_csv` 等旧参数兼容现有部署，但默认目录和构建入口均已切换到 Tianchi。
