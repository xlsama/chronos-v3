---
name: 日志分析
description: 日志分析与错误定位指南。当事件涉及日志查看、错误日志、异常堆栈、应用报错、系统日志、journalctl、syslog、日志轮转、日志搜索、日志关联分析、OOM 日志、内核日志、审计日志、应用启动失败日志时使用。
metadata:
  pattern: pipeline
  domain: observability
  steps: "4"
---

## 执行环境说明

你是一个远程运维 Agent，不在目标服务器上运行。所有操作通过以下工具完成：

- **`ssh_bash(server_id, command)`** — 在**远程目标服务器**上执行 shell 命令（首选）
- **`service_exec(service_id, command)`** — 直连已注册的数据库/缓存/监控服务（无需 CLI 工具）
- **`bash(command)`** — 仅用于本地文本处理、curl 等辅助操作

> 命令中的 `localhost` / `127.0.0.1` 指的是**目标服务器自身**，不是你运行的位置。

## 第零步：定位目标（必须执行）

1. 调用 `list_servers()` 获取可用服务器列表
2. 调用 `list_services()` 获取已注册服务
3. 结合事件描述，确定目标服务器和需要查看的日志类型

## 第一步：系统日志

通过 `ssh_bash(server_id, "...")` 执行：

### journalctl（systemd 系统）

```bash
# 最近 1 小时的错误及以上级别日志
ssh_bash(server_id, "journalctl --since '1 hour ago' -p err --no-pager | tail -50")

# 指定服务的日志
ssh_bash(server_id, "journalctl -u <service-name> --since '1 hour ago' --no-pager | tail -100")

# 按时间范围查看
ssh_bash(server_id, "journalctl --since '2024-01-01 10:00:00' --until '2024-01-01 11:00:00' --no-pager | tail -100")

# 内核日志
ssh_bash(server_id, "journalctl -k --since '1 hour ago' --no-pager | tail -30")

# 启动日志（上次启动）
ssh_bash(server_id, "journalctl -b -1 --no-pager | tail -50")
```

### dmesg（内核消息）

```bash
# 最近的内核消息
ssh_bash(server_id, "dmesg -T | tail -30")

# OOM Kill 记录
ssh_bash(server_id, "dmesg -T | grep -i 'oom\|out of memory\|killed process' | tail -10")

# 硬件/文件系统错误
ssh_bash(server_id, "dmesg -T | grep -iE 'error|fail|fault|I/O' | tail -20")
```

## 第二步：应用日志

### 常见日志路径

```bash
# 列出常见日志目录
ssh_bash(server_id, "ls -la /var/log/ | head -30")

# 应用常见路径
ssh_bash(server_id, "ls -la /var/log/nginx/ /var/log/mysql/ /var/log/postgresql/ 2>/dev/null")

# 查看最近修改的日志文件
ssh_bash(server_id, "find /var/log -name '*.log' -mmin -60 -type f 2>/dev/null | head -20")
```

### 日志搜索与过滤

```bash
# 关键字搜索（不区分大小写）
ssh_bash(server_id, "grep -i 'error\|exception\|fatal\|critical' /var/log/<logfile> | tail -30")

# 按时间戳过滤（适用于常见日志格式）
ssh_bash(server_id, "awk '/2024-01-01 10:/ {found=1} found' /var/log/<logfile> | head -50")

# 统计错误频率
ssh_bash(server_id, "grep -ic 'error' /var/log/<logfile>")

# 最近 N 行日志
ssh_bash(server_id, "tail -100 /var/log/<logfile>")
```

### 结构化日志（JSON）

```bash
# 用 jq 解析 JSON 日志
ssh_bash(server_id, "tail -50 /var/log/<logfile> | jq -r '. | \"\\(.timestamp) [\\(.level)] \\(.message)\"' 2>/dev/null || tail -50 /var/log/<logfile>")

# 过滤特定级别
ssh_bash(server_id, "tail -200 /var/log/<logfile> | jq -r 'select(.level == \"error\" or .level == \"ERROR\")' 2>/dev/null | head -30")
```

## 第三步：容器与服务日志

### Docker 容器日志

```bash
# 容器日志
ssh_bash(server_id, "docker logs --tail 100 --timestamps <容器名>")

# 按时间过滤
ssh_bash(server_id, "docker logs --since '1h' <容器名> 2>&1 | tail -100")

# 搜索错误
ssh_bash(server_id, "docker logs --tail 500 <容器名> 2>&1 | grep -i 'error\|exception\|fatal'")
```

### systemd 服务日志

```bash
ssh_bash(server_id, "journalctl -u <service> --since '1 hour ago' --no-pager | tail -100")
```

## 第四步：日志关联与轮转检查

### 多日志关联

```bash
# 查看同一时间点多个日志文件
ssh_bash(server_id, "echo '=== App Log ==='; grep '10:30' /var/log/app.log | tail -10; echo '=== Nginx Log ==='; grep '10:30' /var/log/nginx/error.log | tail -10; echo '=== System Log ==='; journalctl --since '10:30' --until '10:31' --no-pager 2>/dev/null | tail -10")
```

### 日志轮转检查

```bash
# logrotate 配置
ssh_bash(server_id, "cat /etc/logrotate.conf 2>/dev/null; echo '---'; ls /etc/logrotate.d/ 2>/dev/null")

# 查看特定服务的轮转配置
ssh_bash(server_id, "cat /etc/logrotate.d/<service> 2>/dev/null || echo 'no logrotate config'")

# logrotate 状态（上次轮转时间）
ssh_bash(server_id, "cat /var/lib/logrotate/status 2>/dev/null | tail -20")
```

## 常见错误模式

| 错误模式 | 日志关键字 | 排查方向 |
|---------|-----------|---------|
| OOM Killed | `Out of memory`, `oom-kill`, `Killed process` | dmesg + 进程内存使用 |
| 段错误 | `Segmentation fault`, `segfault`, `core dumped` | dmesg + 应用 core dump |
| 连接拒绝 | `Connection refused` | 目标服务是否运行 + 端口监听 |
| 连接超时 | `Connection timed out`, `timeout` | 网络连通性 + 防火墙 |
| 权限拒绝 | `Permission denied`, `access denied` | 文件权限 + 用户/组 |
| 磁盘满 | `No space left on device` | df -h + du 定位大文件 |
| DNS 失败 | `Name or service not known`, `NXDOMAIN` | DNS 配置 + resolv.conf |
| SSL 错误 | `SSL_ERROR`, `certificate`, `handshake` | 证书过期 + 证书链 |

## 注意事项

- **日志行数控制**：始终用 `tail`、`head` 或 `| tail -N` 限制输出，避免大量日志输出
- **二进制日志**：journalctl 存储的是二进制格式，不要尝试 `cat` journal 文件
- **日志级别**：journalctl `-p` 支持 emerg(0)~debug(7)，常用 `-p err`（≤error）
- **时区注意**：journalctl 默认显示本地时区，`--utc` 可切换 UTC
- **敏感信息**：日志中可能包含密码、Token 等，输出时注意脱敏
