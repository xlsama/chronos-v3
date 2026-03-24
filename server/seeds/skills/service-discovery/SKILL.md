---
name: 服务发现
description: 快速发现服务器上运行的所有服务和完整环境画像。当事件涉及服务器、基础设施、服务、部署、端口、进程、容器、Docker、数据库、缓存、日志、性能、故障、告警、监控、排查、网络、磁盘、内存、CPU、负载、连接、超时、延迟时使用。几乎所有运维事件都需要先了解目标环境，建议在排查开始阶段加载此技能。
metadata:
  pattern: pipeline
  domain: infra
  steps: "4"
---

## 执行环境说明

你是一个远程运维 Agent，不在目标服务器上运行。所有操作通过以下工具完成：

- **`ssh_bash(server_id, command)`** — 在**远程目标服务器**上执行 shell 命令（首选）
- **`service_exec(service_id, command)`** — 直连已注册的数据库/缓存/监控服务（无需 CLI 工具）
- **`bash(command)`** — 仅用于本地文本处理、curl 等辅助操作

> 命令中的 `localhost` / `127.0.0.1` 指的是**目标服务器自身**，不是你运行的位置。

## 第零步：获取目标（必须执行）

先确定可操作的服务器和服务列表：

1. 调用 `list_servers()` 获取可用服务器列表（返回 id、name、host、status）
2. 调用 `list_services()` 获取已注册的数据库/缓存/监控服务（返回 id、name、service_type、host、port、status）
3. 结合事件描述和知识库上下文，确定本次排查的目标服务器

## 全局优先级（必须遵守）

- 只要目标机出现 `docker.service`、`containerd.service`、`dockerd`、`containerd-shim`、`Dockerfile`、镜像构建脚本等容器化证据，**下一步必须优先走 Docker**。
- 在这种情况下，先读取 `docker-container` 技能，再执行 Docker 诊断；不要先跳去看应用进程细节。
- 如果 `docker ps` 失败，不要立刻认定“没有容器”；要继续区分是 **PATH 缺失**、**daemon 未启动**、还是 **权限问题**。
- 首轮 Docker / systemd / curl 探测必须保留原始 stderr，不要用 `2>/dev/null` 或 `| head ... || echo ...` 把真实错误吞掉。
- 如果首轮 Docker 探测报 `permission denied`，先把它识别为权限问题；必要时走审批后改用 `sudo docker ...` 验证，不要把空输出或权限错误当成“没有容器”。

## 第一步：服务器全貌（必须执行）

将以下命令整体作为一条 command 传入 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 主机信息 ====='; hostname; hostname -I 2>&1; uname -a; cat /etc/os-release 2>&1 | head -5; echo ''; echo '===== 资源概况 ====='; uptime; nproc; free -h; df -h -x tmpfs -x devtmpfs 2>&1 || df -h; echo ''; echo '===== systemd 服务 ====='; systemctl list-units --type=service --state=running --no-pager --no-legend 2>&1 | head -40 || echo 'systemd not available'; echo ''; echo '===== Supervisor ====='; supervisorctl status 2>&1 || echo 'supervisorctl not available'; echo ''; echo '===== PM2 ====='; pm2 list 2>&1 || echo 'pm2 not available'; echo ''; echo '===== Docker 服务 ====='; systemctl status docker --no-pager 2>&1 | head -20 || echo 'docker service status unavailable'; echo ''; echo '===== Docker 容器 ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1; echo ''; echo '===== 全部容器（含停止） ====='; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}' 2>&1; echo ''; echo '===== 监听端口 ====='; ss -tlnp 2>&1 || netstat -tlnp 2>&1 || echo 'ss/netstat not available'; echo ''; echo '===== Crontab ====='; crontab -l 2>&1 || echo 'no crontab'; echo ''; echo '===== Top 进程(内存) ====='; ps -eo pid,user,%cpu,%mem,comm --sort=-%mem | head -15
```

如果上一步发现 Docker 服务正在运行、存在容器、或容器相关进程/构建脚本，请**立即切换到 `docker-container` 技能**继续排查，不要先深入应用进程层。

## 第二步：服务探测（根据第一步结果选择执行）

### 优先：已注册服务（通过 service_exec）

对 `list_services()` 返回的在线服务，用 `service_exec(service_id, command)` 快速验活：

| 服务类型 | 验活命令 |
|---------|---------|
| PostgreSQL | `SELECT version()` |
| MySQL | `SELECT version()` |
| Redis | `PING` |
| MongoDB | `{"ping": 1}` |
| Elasticsearch | `GET /_cluster/health` |
| Prometheus | `up` |

### 备选：未注册服务（通过 ssh_bash）

根据第一步发现的端口和进程，对未在 `list_services()` 中注册的服务，通过 `ssh_bash(server_id, command)` 探测：

```bash
# MySQL/MariaDB（端口 3306）
mysql -u root -e 'SELECT version();' 2>&1

# PostgreSQL（端口 5432）
psql -U postgres -c 'SELECT version();' 2>&1

# Redis（端口 6379）
redis-cli PING 2>&1

# MongoDB（端口 27017）
mongosh --eval 'db.runCommand({ping:1})' 2>&1
```

> 数据库详细排查请参考 **数据库排查** 技能。

## 第三步：错误日志速查（可选，按需执行）

如果需要检查近期异常，通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 最近系统错误日志 ====='; journalctl --since '1h ago' -p err --no-pager 2>&1 | tail -30; echo ''; echo '===== Nginx 错误日志 ====='; tail -20 /var/log/nginx/error.log 2>&1; echo ''; echo '===== Docker 异常容器 ====='; docker ps -a --filter 'status=exited' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>&1 | head -10
```

## 结果整理

执行完毕后，用表格汇总服务器画像：

| 类别 | 内容 |
|------|------|
| 主机 | hostname、IP、OS |
| 资源 | CPU 核数、内存、磁盘 |
| 服务 | 运行中的 systemd/supervisor/pm2/docker 服务 |
| 数据库 | 类型、库列表、表数量（已注册/未注册） |
| 端口 | 关键监听端口及对应进程 |
| 定时任务 | crontab 条目 |
| 异常 | 近期错误日志、退出的容器 |

如果发现了多个服务之间存在依赖关系，用 Mermaid flowchart 可视化服务间调用链。
