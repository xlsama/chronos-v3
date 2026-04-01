# ETL Pipeline Troubleshooting Test Case

## 场景说明

测试 Chronos V3 Agent 排查跨库 ETL 数据链路问题的能力。

### 数据库拓扑

```
┌─────────────┐    ETL Script 1    ┌──────────────┐    ETL Script 2    ┌──────────────┐
│ mysql-source │ ─────────────────> │ mysql-staging │ ─────────────────> │ mysql-target  │
│  port:13307  │  过滤 completed   │  port:13308   │  按日期/区域聚合  │  port:13309   │
│  source_db   │  JOIN products    │  staging_db   │                   │  target_db    │
│  200 orders  │                   │  clean_orders │                   │  daily_sales  │
│  (20cancelled)                   │  (应=180条)   │                   │  summary      │
└─────────────┘                    └──────────────┘                    └──────────────┘
```

### Bug 注入

1. 先运行正确 ETL：source(200) → 过滤 → staging(180) → 聚合 → target(180)
2. 再运行 buggy ETL：source(200) → **不过滤** → staging(200)，**不重跑聚合** → target 仍=180
3. 数据不一致：staging(200) ≠ target.SUM(order_count)(180)

### 事件提示词

```
ETL 数据管道异常告警：目标库 daily_sales_summary 的聚合总订单数与清洗库 clean_orders
的总记录数不匹配。target_db 上 SELECT SUM(order_count) FROM daily_sales_summary 结果为 180，
但 staging_db 上 SELECT COUNT(*) FROM clean_orders 结果为 200。
差异 20 条记录，请排查是哪个 ETL 环节出了问题。
相关服务: mysql-etl-source, mysql-etl-staging, mysql-etl-target
```

## 运行方式

```bash
# 1. 启动开发基础设施（PG + Redis）
docker compose -f docker-compose.dev.yml up -d --wait

# 2. 启动 Agent 目标数据库
docker compose -f server/tests/agent/docker-compose.agent.yml up -d --wait

# 3. 启动 ETL 场景 MySQL 实例
docker compose -f server/tests/agent/cases/etl_pipeline/docker-compose.etl.yml up -d --wait

# 4. 设置 API Key
export DASHSCOPE_API_KEY=sk-xxx

# 5. 运行测试
cd server && uv run pytest tests/agent/cases/etl_pipeline/ -x -v -m agent
```

## 测试验证点

| # | 验证项 | 类型 |
|---|--------|------|
| 1 | 知识库项目创建成功 | 硬断言 |
| 2 | 文档上传并索引成功 | 硬断言 |
| 3 | import-connections 提取出 ≥3 个 MySQL 服务 | 硬断言 |
| 4 | 正确 ETL 后 staging=180 | 硬断言 |
| 5 | buggy ETL 后 staging=200, target 仍=180 | 硬断言 |
| 6 | Agent 进入 investigating 状态 | 硬断言 |
| 7 | Agent 调用 service_exec 查询数据库 | 硬断言 |
| 8 | Agent 达到终态 (resolved/stopped/error) | 硬断言 |
| 9 | Agent 输出提及关键数字/关键词 | 软断言 (warning) |

## 文件说明

| 文件 | 说明 |
|------|------|
| `docker-compose.etl.yml` | 3 个 MySQL 实例 |
| `init/source_init.sql` | 源库初始化：200 orders + 5 products |
| `init/staging_init.sql` | 清洗库初始化：空 clean_orders 表 |
| `init/target_init.sql` | 目标库初始化：空 daily_sales_summary 表 |
| `etl_scripts/etl_correct.py` | 正确 ETL（过滤 cancelled + 聚合） |
| `etl_scripts/etl_buggy.py` | 错误 ETL（不过滤 + 不重跑聚合） |
| `knowledge_docs/etl_architecture.md` | 知识库文档：拓扑、连接、校验规则 |
| `conftest.py` | MySQL 连接配置 + 健康检查 fixture |
| `test_etl_pipeline.py` | 主测试文件（9 阶段完整流程） |
