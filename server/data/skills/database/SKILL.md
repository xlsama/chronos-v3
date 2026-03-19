---
name: 数据库排查
description: 数据库相关操作指南，适用于 PostgreSQL、MySQL、Redis。当事件涉及任何数据库相关操作时使用。
metadata:
  pattern: pipeline
  domain: database
  steps: "3"
---

数据库排查必须通过 CLI 工具直接查询运行时状态，**禁止通过读源码/构建产物推断数据库信息**。

## 反模式（禁止）

以下做法是**错误的**，不要执行：
- `cat app/db/schema.ts` 或 `cat app/models/*.py` → 试图从源码获取表结构
- `cat dist/db/index.js` → 从构建产物获取连接串
- `cat drizzle/*.sql` 或 `cat alembic/versions/*.py` → 从迁移文件获取表结构
- `cat .env` 或 `cat docker-compose.yml` → 从配置文件获取连接串后直接使用，不验证

源码反映的是代码意图，不是运行时实际状态。迁移可能未执行、配置可能被覆盖、环境变量可能不同。

## 第一步：发现数据库（必须执行）

一次调用同时获取端口监听和 Docker 容器信息：

```bash
echo "=== 端口监听 ===" && ss -tlnp | grep -E ':(5432|3306|6379|27017) '; echo "=== Docker 容器 ===" && docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null | grep -iE '(postgres|mysql|mariadb|redis|mongo)' || true
```

## 第二步：获取连接凭据

从服务器环境变量或配置中获取，不要从源码文件获取：

```bash
echo "=== 环境变量 ===" && env | grep -iE '(DB_|DATABASE|PG|POSTGRES|MYSQL|REDIS)'; echo "=== 应用进程环境 ===" && for pid in $(pgrep -f '<进程关键词>'); do echo "--- PID $pid ---"; cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep -iE '(DB_|DATABASE|PG|POSTGRES|MYSQL|REDIS)'; done
```

补充方式（按需选用）：

```bash
# 从 systemd 服务配置获取
systemctl show <服务名> --property=Environment

# 从 Docker 容器环境变量获取
docker exec <容器名> env | grep -iE '(DB_|DATABASE|PG|POSTGRES|MYSQL|REDIS)'
```

## 第三步：用 CLI 工具查询

### PostgreSQL

**数据库概览（一次拿全）**：数据库列表 + 连接数 + 等待锁

```bash
psql -U <user> -h 127.0.0.1 -c "\l" -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC;" -c "SELECT count(*) AS waiting_locks FROM pg_locks WHERE NOT granted;"
```

**表概览（一次拿全）**：表名 + 大小 + 行数估算

```bash
psql -U <user> -h 127.0.0.1 -d <dbname> -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size, n_live_tup AS est_rows FROM pg_stat_user_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 20;"
```

**表结构 + 样例数据**：

```bash
psql -U <user> -h 127.0.0.1 -d <dbname> -c "\d <表名>" -c "SELECT * FROM <表名> LIMIT 5;"
```

**慢查询 + 锁分析**：

```bash
psql -U <user> -h 127.0.0.1 -d <dbname> -c "SELECT pid, now()-query_start AS duration, state, LEFT(query,80) AS query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10;" -c "SELECT pid, mode, relation::regclass, granted FROM pg_locks WHERE NOT granted;"
```

### MySQL

**数据库概览**：数据库列表 + 活跃查询

```bash
mysql -u<user> -p<password> -h 127.0.0.1 -e "SHOW DATABASES; SELECT user, host, db, command, time, LEFT(info,80) AS query FROM information_schema.processlist WHERE command != 'Sleep' ORDER BY time DESC LIMIT 10;"
```

**表概览**：表名 + 大小 + 行数

```bash
mysql -u<user> -p<password> -h 127.0.0.1 -e "SELECT table_name, table_rows, ROUND(data_length/1024/1024,2) AS data_mb, ROUND(index_length/1024/1024,2) AS index_mb FROM information_schema.tables WHERE table_schema='<dbname>' ORDER BY data_length DESC LIMIT 20;"
```

**表结构 + 样例数据**：

```bash
mysql -u<user> -p<password> -h 127.0.0.1 <dbname> -e "DESCRIBE <表名>; SELECT * FROM <表名> LIMIT 5;"
```

**慢查询 + 锁**：

```bash
mysql -u<user> -p<password> -h 127.0.0.1 -e "SHOW VARIABLES LIKE 'slow_query%'; SHOW VARIABLES LIKE 'long_query_time'; SELECT * FROM information_schema.INNODB_LOCKS;" 2>/dev/null; mysql -u<user> -p<password> -h 127.0.0.1 -e "SELECT trx_id, trx_state, trx_started, trx_wait_started, trx_mysql_thread_id FROM information_schema.INNODB_TRX;" 2>/dev/null
```

### Redis

**全局概览（一条拿全）**：用一次 `INFO` + grep 提取关键指标

```bash
redis-cli INFO | grep -E '(redis_version|connected_clients|blocked_clients|used_memory_human|maxmemory_human|mem_fragmentation_ratio|instantaneous_ops_per_sec|keyspace_hits|keyspace_misses|db[0-9]+:)'
```

**Key 扫描 + 类型和 TTL**：

```bash
redis-cli --scan --pattern '<前缀>*' | head -20 | while read key; do echo "$key | type=$(redis-cli TYPE $key) | ttl=$(redis-cli TTL $key)"; done
```

**慢日志**：

```bash
redis-cli SLOWLOG GET 10
```

## 注意事项

- **Docker 场景**: 如果数据库跑在 Docker 容器中，在命令前加 `docker exec -i <容器名>` 前缀，例如 `docker exec -i pg_container psql -U postgres -c "\l"`
- 如果数据库在远程服务器，需要通过 `-h <host> -p <port>` 指定连接地址
- 查数据时始终加 `LIMIT`，避免大表全量扫描
- Redis 生产环境用 `--scan` 代替 `KEYS *`
- 如果有 Redis 密码，在命令中加 `-a <password>`
