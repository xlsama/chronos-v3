---
name: 数据库排查
description: 数据库与数据存储排查指南，覆盖 PostgreSQL、MySQL、Redis、MongoDB、Elasticsearch、Prometheus 六种服务类型。
when_to_use: >-
  当事件涉及数据库连接异常、慢查询、锁等待、死锁、主从延迟、复制异常、内存溢出、
  缓存穿透/击穿/雪崩、索引失效、表空间、磁盘占用、连接耗尽、QPS 异常、集群健康、
  分片异常、查询超时、数据一致性等数据库相关问题时使用。
  不适用于：纯应用层逻辑错误、网络不通（应先排查网络）。
tags:
  - database
  - storage
related_services:
  - postgresql
  - mysql
  - redis
  - mongodb
  - elasticsearch
  - prometheus
metadata:
  pattern: pipeline
  domain: database
  steps: "3"
---

## 执行环境与工具选择

你是远程运维 Agent。数据库排查有两种工具，**优先使用 service_exec**：

### service_exec(service_id, command) — 首选

直连已注册服务，无需服务器上安装 CLI 工具。先调用 `list_services()` 发现可用服务。

各类型命令格式：

| 服务类型 | 命令格式 | 示例 |
|---------|---------|------|
| PostgreSQL | 纯 SQL（SELECT/SHOW/EXPLAIN/WITH） | `SELECT version()` |
| MySQL | 纯 SQL（SELECT/SHOW/EXPLAIN/DESCRIBE/WITH） | `SHOW DATABASES` |
| Redis | 原生 Redis 命令 | `INFO server` |
| MongoDB | JSON 命令文档 | `{"ping": 1}` |
| Elasticsearch | `METHOD /path [json_body]` | `GET /_cluster/health` |
| Prometheus | PromQL 表达式 | `up{job="prometheus"}` |

### ssh_bash(server_id, command) — 备选

用于未注册服务或需要 OS 级数据（进程、磁盘、日志等）。

## 反模式（禁止）

- **禁止从源码推断数据库状态**：不要 `cat schema.ts`、`cat models.py`、`cat .env`、`cat docker-compose.yml` 来获取数据库信息。源码反映代码意图，不是运行时状态
- **禁止在 service_exec 中使用 psql 元命令**：`\l`、`\d`、`\dt`、`\du` 等不被支持（asyncpg 只接受纯 SQL）
- **禁止在 service_exec 中使用 mysql 元命令**：`use db`、`source file` 等不被支持

---

## PostgreSQL

### service_exec 方式（优先）

**数据库列表**：
```sql
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database WHERE datistemplate = false ORDER BY pg_database_size(datname) DESC
```

**表概览**：
```sql
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size, n_live_tup AS est_rows FROM pg_stat_user_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 30
```

**表结构**：
```sql
SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '<表名>' ORDER BY ordinal_position
```

**连接统计**：
```sql
SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC
```

**锁分析**：
```sql
SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query, blocking.pid AS blocking_pid, blocking.query AS blocking_query FROM pg_stat_activity blocked JOIN pg_locks bl ON blocked.pid = bl.pid JOIN pg_locks kl ON bl.relation = kl.relation AND bl.pid != kl.pid JOIN pg_stat_activity blocking ON kl.pid = blocking.pid WHERE NOT bl.granted
```

**慢查询/活跃查询**：
```sql
SELECT pid, now() - query_start AS duration, state, LEFT(query, 100) AS query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10
```

**索引使用率**：
```sql
SELECT schemaname, tablename, indexrelname, idx_scan, idx_tup_read, idx_tup_fetch FROM pg_stat_user_indexes ORDER BY idx_scan ASC LIMIT 20
```

**Vacuum 状态**：
```sql
SELECT schemaname, relname, last_vacuum, last_autovacuum, vacuum_count, autovacuum_count, n_dead_tup FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 20
```

### ssh_bash 方式（备选）

```bash
# 数据库列表
psql -U <user> -h 127.0.0.1 -l

# 表结构
psql -U <user> -h 127.0.0.1 -d <dbname> -c "\d <表名>"

# 慢查询 + 锁
psql -U <user> -h 127.0.0.1 -d <dbname> -c "SELECT pid, now()-query_start AS duration, state, LEFT(query,80) FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10;"
```

### 常见问题排查

| 问题 | 排查 SQL |
|------|---------|
| 连接耗尽 | `SELECT count(*) FROM pg_stat_activity` + `SHOW max_connections` |
| 锁竞争 | 上方锁分析 SQL |
| 主从延迟 | `SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag`（从库执行） |
| 高 CPU 查询 | 活跃查询 SQL，关注 duration 长的 |
| 磁盘空间 | `SELECT pg_size_pretty(pg_database_size(current_database()))` + `ssh_bash` 查 `df -h` |
| Vacuum 异常 | Vacuum 状态 SQL，关注 n_dead_tup 高的表 |

---

## MySQL

### service_exec 方式（优先）

**数据库列表**：
```sql
SHOW DATABASES
```

**表概览**：
```sql
SELECT table_name, table_rows, ROUND(data_length/1024/1024, 2) AS data_mb, ROUND(index_length/1024/1024, 2) AS index_mb FROM information_schema.tables WHERE table_schema = '<dbname>' ORDER BY data_length DESC LIMIT 30
```

**表结构**：
```sql
DESCRIBE <表名>
```

**活跃查询**：
```sql
SELECT id, user, host, db, command, time, LEFT(info, 100) AS query FROM information_schema.processlist WHERE command != 'Sleep' ORDER BY time DESC LIMIT 10
```

**锁分析**：
```sql
SELECT trx_id, trx_state, trx_started, trx_wait_started, trx_mysql_thread_id FROM information_schema.INNODB_TRX
```

**InnoDB 状态**：
```sql
SHOW ENGINE INNODB STATUS
```

**慢查询配置**：
```sql
SHOW VARIABLES LIKE 'slow_query%'
```

**主从状态**：
```sql
SHOW SLAVE STATUS
```

### ssh_bash 方式（备选）

```bash
# 数据库列表
mysql -u<user> -p<password> -h 127.0.0.1 -e "SHOW DATABASES;"

# 表概览
mysql -u<user> -p<password> -h 127.0.0.1 -e "SELECT table_name, table_rows, ROUND(data_length/1024/1024,2) AS data_mb FROM information_schema.tables WHERE table_schema='<dbname>' ORDER BY data_length DESC LIMIT 20;"
```

### 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 连接耗尽 | `SHOW STATUS LIKE 'Threads_connected'` + `SHOW VARIABLES LIKE 'max_connections'` |
| 死锁 | `SHOW ENGINE INNODB STATUS` 查看 LATEST DETECTED DEADLOCK 段 |
| 主从延迟 | `SHOW SLAVE STATUS` 关注 Seconds_Behind_Master |
| InnoDB 缓冲池 | `SHOW STATUS LIKE 'Innodb_buffer_pool%'` |
| Binlog 磁盘占用 | `SHOW BINARY LOGS` |
| 表碎片 | `SELECT table_name, data_free FROM information_schema.tables WHERE table_schema='<dbname>' AND data_free > 0 ORDER BY data_free DESC` |

---

## Redis

### service_exec 方式（优先）

**全局概览**：
```
INFO server
```

```
INFO memory
```

```
INFO clients
```

```
INFO keyspace
```

```
INFO stats
```

**客户端连接列表**：
```
CLIENT LIST
```

**慢日志**：
```
SLOWLOG GET 10
```

**Key 扫描**（用 SCAN 不用 KEYS）：
```
SCAN 0 MATCH <前缀>* COUNT 20
```

**Key 内存占用**：
```
MEMORY USAGE <key>
```

**配置查看**：
```
CONFIG GET maxmemory
```

```
CONFIG GET maxmemory-policy
```

### ssh_bash 方式（备选）

```bash
# 全局概览
redis-cli INFO | grep -E '(redis_version|connected_clients|blocked_clients|used_memory_human|maxmemory_human|mem_fragmentation_ratio|instantaneous_ops_per_sec|keyspace_hits|keyspace_misses|db[0-9]+:)'

# 慢日志
redis-cli SLOWLOG GET 10

# 大 Key 扫描
redis-cli --bigkeys --no-auth-warning 2>/dev/null
```

### 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 内存溢出/淘汰 | `INFO memory` 关注 used_memory vs maxmemory + `CONFIG GET maxmemory-policy` |
| 高延迟 | `SLOWLOG GET 20` + `INFO stats` 关注 instantaneous_ops_per_sec |
| 连接耗尽 | `INFO clients` 关注 connected_clients + `CONFIG GET maxclients` |
| 缓存穿透/击穿/雪崩 | `INFO stats` 关注 keyspace_hits vs keyspace_misses 计算命中率 |
| 持久化问题 | `INFO persistence` 关注 rdb_last_bgsave_status、aof_last_write_status |
| 大 Key | `MEMORY USAGE <key>` 或 ssh_bash `redis-cli --bigkeys` |

---

## MongoDB

### service_exec 方式

命令格式为 JSON 文档，传给 `db.command()`。

**服务器状态**：
```json
{"serverStatus": 1}
```

**数据库列表**：
```json
{"listDatabases": 1}
```

**集合统计**：
```json
{"collStats": "<collection_name>"}
```

**当前操作**：
```json
{"currentOp": 1}
```

**索引统计**：
```json
{"aggregate": "<collection_name>", "pipeline": [{"$indexStats": {}}], "cursor": {}}
```

**查询数据**：
```json
{"find": "<collection_name>", "filter": {}, "limit": 10}
```

### 常见问题排查

| 问题 | 排查命令 |
|------|---------|
| 慢查询 profiling | `{"profile": -1}` 查看当前级别；`{"aggregate": "system.profile", "pipeline": [{"$sort": {"millis": -1}}, {"$limit": 10}], "cursor": {}}` |
| 锁竞争 | `{"serverStatus": 1}` 关注 globalLock、currentQueue 段 |
| 副本集延迟 | `{"replSetGetStatus": 1}` 关注 members 的 optimeDate 差异 |
| WiredTiger 缓存 | `{"serverStatus": 1}` 关注 wiredTiger.cache 段 |

---

## Elasticsearch

### service_exec 方式

命令格式为 `METHOD /path [json_body]`。

**集群健康**：
```
GET /_cluster/health
```

**节点统计**：
```
GET /_nodes/stats
```

**索引列表**：
```
GET /_cat/indices?v&s=store.size:desc
```

**分片分配**：
```
GET /_cat/shards?v
```

**待处理任务**：
```
GET /_cluster/pending_tasks
```

**热线程**：
```
GET /_nodes/hot_threads
```

**搜索查询**：
```
POST /<index>/_search {"query": {"match_all": {}}, "size": 5}
```

### 常见问题排查

| 问题 | 排查命令 |
|------|---------|
| Red/Yellow 集群 | `GET /_cluster/health` + `GET /_cat/shards?v&h=index,shard,prirep,state,unassigned.reason` |
| 未分配分片 | `GET /_cluster/allocation/explain` |
| JVM 堆压力 | `GET /_nodes/stats/jvm` 关注 heap_used_percent |
| 磁盘水位线 | `GET /_cluster/settings?include_defaults=true&flat_settings=true` 搜索 watermark |

---

## Prometheus

### service_exec 方式

命令格式为 PromQL 表达式字符串。

**目标存活检测**：
```
up
```

**指定 Job 状态**：
```
up{job="<job_name>"}
```

**告警规则查询**：
```
ALERTS{alertstate="firing"}
```

**CPU 使用率（Node Exporter）**：
```
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

**内存使用率**：
```
(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100
```

**磁盘使用率**：
```
(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100
```

### 使用场景

- 事件排查中关联指标：用 PromQL 查询事件发生时间段的资源指标变化
- 监控自身健康：`up{job="prometheus"}` 检查 Prometheus 本身是否正常
- 告警关联：`ALERTS{alertstate="firing"}` 查看当前触发的告警

---

## 通用注意事项

- **查询加 LIMIT**：SQL 查询始终加 LIMIT 避免大表全量扫描
- **Redis 用 SCAN 不用 KEYS**：生产环境 `KEYS *` 会阻塞，用 `SCAN 0 MATCH <pattern> COUNT 100`
- **Docker 场景**：服务跑在 Docker 中且未注册 service 时，通过 `ssh_bash` + `docker exec -i <容器名> <命令>` 执行
- **凭据获取**：通过 `ssh_bash` 执行 `env | grep -iE '(DB_|DATABASE|PG|POSTGRES|MYSQL|REDIS)'` 或 `docker inspect <容器名>` 获取
- **先只读后写入**：排查阶段始终使用只读查询，需要修复操作时明确告知用户并等待确认
