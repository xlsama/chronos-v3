---
name: 服务发现
description: 快速发现服务器上运行的所有服务、数据库、容器和端口，一次性获取完整服务器画像。当需要了解服务器上有什么、排查前先摸清环境、确认数据库/服务部署位置，或用户问"这台机器跑了什么"、"库在哪台机器上"时使用。
metadata:
  pattern: pipeline
  domain: infra
  steps: "3"
---

当你需要了解一台服务器上运行了什么服务时，按以下步骤执行。适用场景：
- 排查前需要先摸清目标服务器环境
- 用户问"这台服务器上跑了什么服务"
- 需要建立服务依赖关系的全局视图
- 首次接触一台未在 AGENTS.md 中记录的服务器
- 需要先确认数据库跑在哪台机器、有哪些库表，再决定下一步查询路径

每一步都是一条可以直接传入 bash(server_id, command) 执行的命令。

## 第一步：服务器全貌（必须执行）

将以下命令整体作为一条 command 传入 bash() 执行：

```bash
echo '===== 主机信息 ====='; hostname; hostname -I 2>/dev/null; uname -a; cat /etc/os-release 2>/dev/null | head -5; echo ''; echo '===== 资源概况 ====='; uptime; nproc; free -h; df -h -x tmpfs -x devtmpfs 2>/dev/null || df -h; echo ''; echo '===== systemd 服务 ====='; command -v systemctl >/dev/null 2>&1 && systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | head -40 || echo 'systemd not available'; echo ''; echo '===== Supervisor ====='; supervisorctl status 2>/dev/null || echo 'not available'; echo ''; echo '===== PM2 ====='; pm2 list 2>/dev/null || echo 'not available'; echo ''; echo '===== Docker 容器 ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo 'not available'; echo ''; echo '===== 监听端口 ====='; ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || echo 'ss/netstat not available'; echo ''; echo '===== Crontab ====='; crontab -l 2>/dev/null || echo 'no crontab'; echo ''; echo '===== Top 进程(内存) ====='; ps -eo pid,user,%cpu,%mem,comm --sort=-%mem | head -15
```

## 第二步：数据库探测（根据第一步结果选择执行）

根据第一步发现的端口和进程，选择性执行对应数据库探测。

**MySQL/MariaDB**（端口 3306 或 mysqld 进程）：
```bash
echo '===== MySQL 数据库列表 ====='; mysql -u root -e 'SHOW DATABASES;' 2>/dev/null || mysql -e 'SHOW DATABASES;' 2>/dev/null || echo 'mysql connect failed'; echo ''; echo '===== MySQL 各库表数量 ====='; mysql -u root -e "SELECT TABLE_SCHEMA, COUNT(*) as table_count FROM information_schema.TABLES WHERE TABLE_SCHEMA NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY TABLE_SCHEMA;" 2>/dev/null || echo 'skipped'
```

**PostgreSQL**（端口 5432 或 postgres 进程）：
```bash
echo '===== PostgreSQL 数据库列表 ====='; psql -U postgres -l 2>/dev/null || echo 'psql connect failed'; echo ''; echo '===== PostgreSQL 各库表数量 ====='; psql -U postgres -c "SELECT schemaname, COUNT(*) as table_count FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') GROUP BY schemaname;" 2>/dev/null || echo 'skipped'
```

**Redis**（端口 6379 或 redis-server 进程）：
```bash
echo '===== Redis 信息 ====='; redis-cli INFO server 2>/dev/null | grep -E '(redis_version|connected_clients|used_memory_human)' || echo 'redis not available'; echo ''; echo '===== Redis 数据库 ====='; redis-cli INFO keyspace 2>/dev/null || echo 'skipped'
```

## 第三步：错误日志速查（可选，按需执行）

如果需要检查近期异常：

```bash
echo '===== 最近系统错误日志 ====='; journalctl --since '1h ago' -p err --no-pager 2>/dev/null | tail -30 || echo 'journalctl not available'; echo ''; echo '===== Nginx 错误日志 ====='; tail -20 /var/log/nginx/error.log 2>/dev/null || echo 'no nginx error log'; echo ''; echo '===== Docker 异常容器 ====='; docker ps -a --filter 'status=exited' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null | head -10 || echo 'docker not available'
```

## 结果整理

执行完毕后，用表格汇总服务器画像：

| 类别 | 内容 |
|------|------|
| 主机 | hostname、IP、OS |
| 资源 | CPU 核数、内存、磁盘 |
| 服务 | 运行中的 systemd/supervisor/pm2/docker 服务 |
| 数据库 | 类型、库列表、表数量 |
| 端口 | 关键监听端口及对应进程 |
| 定时任务 | crontab 条目 |
| 异常 | 近期错误日志、退出的容器 |

如果发现了多个服务之间存在依赖关系，用 Mermaid flowchart 可视化服务间调用链。
