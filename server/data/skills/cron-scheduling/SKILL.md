---
name: 定时任务排查
description: 定时任务排查指南。当事件涉及定时任务未执行、crontab 配置问题、systemd timer 异常、计划任务输出丢失、任务执行时间异常、任务并发冲突、at/batch 任务、anacron、环境变量差异导致任务失败时使用。
metadata:
  pattern: pipeline
  domain: system
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
3. 结合事件描述，确定目标服务器和问题任务

## 第一步：发现所有定时任务

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 当前用户 Crontab ====='; crontab -l 2>/dev/null || echo 'no crontab'; echo ''; echo '===== 系统 Crontab ====='; cat /etc/crontab 2>/dev/null; echo ''; echo '===== /etc/cron.d/ ====='; ls -la /etc/cron.d/ 2>/dev/null; for f in /etc/cron.d/*; do echo "--- $f ---"; cat "$f" 2>/dev/null; done; echo ''; echo '===== 周期目录 ====='; echo 'hourly:'; ls /etc/cron.hourly/ 2>/dev/null; echo 'daily:'; ls /etc/cron.daily/ 2>/dev/null; echo 'weekly:'; ls /etc/cron.weekly/ 2>/dev/null; echo 'monthly:'; ls /etc/cron.monthly/ 2>/dev/null; echo ''; echo '===== Systemd Timers ====='; systemctl list-timers --all --no-pager 2>/dev/null; echo ''; echo '===== at 队列 ====='; atq 2>/dev/null || echo 'at not available'
```

### 其他用户的 crontab

```bash
# 列出所有用户的 crontab
ssh_bash(server_id, "for u in $(cut -d: -f1 /etc/passwd); do c=$(crontab -u $u -l 2>/dev/null); [ -n \"$c\" ] && echo \"=== $u ===\" && echo \"$c\"; done")
```

## 第二步：执行日志检查

### Cron 日志

```bash
# Debian/Ubuntu
ssh_bash(server_id, "grep CRON /var/log/syslog 2>/dev/null | tail -30")

# CentOS/RHEL
ssh_bash(server_id, "grep CRON /var/log/cron 2>/dev/null | tail -30")

# journalctl
ssh_bash(server_id, "journalctl -u cron --since '24 hours ago' --no-pager 2>/dev/null | tail -30")
ssh_bash(server_id, "journalctl -u crond --since '24 hours ago' --no-pager 2>/dev/null | tail -30")

# 搜索特定任务的执行记录
ssh_bash(server_id, "grep '<关键字或命令片段>' /var/log/syslog /var/log/cron 2>/dev/null | tail -20")
```

### Cron 邮件检查

```bash
# 检查用户邮箱（cron 默认将输出发送到邮箱）
ssh_bash(server_id, "ls -la /var/mail/ 2>/dev/null; cat /var/mail/<用户> 2>/dev/null | tail -50")
```

### Systemd Timer 日志

```bash
# Timer 对应 service 的执行日志
ssh_bash(server_id, "journalctl -u <timer-name>.service --since '24 hours ago' --no-pager | tail -30")

# Timer 上次/下次执行时间
ssh_bash(server_id, "systemctl show <timer-name>.timer --property=LastTriggerUSec,NextElapseUSec --no-pager 2>/dev/null")
```

## 第三步：环境差异排查

### Cron 环境 vs 登录环境

```bash
# 查看 cron 的 PATH（通常非常有限）
ssh_bash(server_id, "grep -E '^PATH|^SHELL|^MAILTO|^HOME' /etc/crontab 2>/dev/null")

# 对比登录环境的 PATH
ssh_bash(server_id, "echo $PATH")

# 测试命令在 cron 最小环境下是否可用
ssh_bash(server_id, "env -i PATH=/usr/bin:/bin which <命令> 2>/dev/null || echo 'command not found in minimal PATH'")
```

### 常见环境问题

```bash
# 确认 cron 服务运行中
ssh_bash(server_id, "systemctl status cron 2>/dev/null || systemctl status crond 2>/dev/null || service cron status 2>/dev/null")

# 时区检查
ssh_bash(server_id, "timedatectl 2>/dev/null || date")

# 脚本权限检查
ssh_bash(server_id, "ls -la <脚本路径>")

# 脚本可执行性
ssh_bash(server_id, "file <脚本路径>; head -1 <脚本路径>")
```

## 第四步：任务并发与锁

```bash
# 检查任务是否仍在运行（上次执行未结束）
ssh_bash(server_id, "ps aux | grep '<任务命令>' | grep -v grep")

# 检查常见锁文件
ssh_bash(server_id, "ls -la /var/lock/ /var/run/ /tmp/ 2>/dev/null | grep -i '<任务名>'")

# flock 锁（如果任务使用 flock 防并发）
ssh_bash(server_id, "lsof /var/lock/<锁文件> 2>/dev/null")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 任务未执行 | cron 服务状态 + 日志搜索 + crontab 语法验证 + 权限检查 |
| PATH 问题 | crontab 中使用绝对路径或在开头设置 `PATH=` |
| 输出丢失 | 检查 MAILTO 设置 + 重定向到文件（`>> /var/log/xxx.log 2>&1`） |
| 权限不足 | 脚本可执行权限 + 运行用户权限 + 文件/目录访问权限 |
| 时区差异 | `timedatectl` 确认系统时区 + crontab 中的 `CRON_TZ` |
| 并发冲突 | 检查上次任务是否仍在运行 + flock 锁机制 |
| systemd timer 不触发 | `systemctl status` + `systemctl show` 查 LastTriggerUSec |
| at 任务未执行 | `atd` 服务状态 + `atq` 队列检查 |

## 注意事项

- **先只读后操作**：排查阶段不修改 crontab、不 enable/disable timer
- **crontab 语法**：分 时 日 月 周 命令，注意 `*` 和范围写法
- **% 转义**：crontab 中 `%` 有特殊含义（换行），需要用 `\%` 转义
- **日志保留**：部分系统 cron 日志按天轮转，历史记录可能已被清理
- **anacron**：对于非持续运行的服务器，anacron 确保错过的任务在启动后执行
