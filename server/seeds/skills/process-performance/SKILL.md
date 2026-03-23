---
name: 进程与性能排查
description: 进程与系统性能排查指南。当事件涉及 CPU 使用率高、内存占用高、进程挂起、僵尸进程、OOM Killer、I/O 等待高、负载飙升、文件描述符耗尽、线程数过多、进程崩溃、core dump、系统卡顿、swap 使用率高时使用。
metadata:
  pattern: pipeline
  domain: system
  steps: "5"
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
3. 结合事件描述，确定目标服务器和性能问题类型

## 第一步：系统概况

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 系统负载 ====='; uptime; echo ''; echo '===== CPU 信息 ====='; nproc; cat /proc/cpuinfo | grep 'model name' | head -1; echo ''; echo '===== 内存概况 ====='; free -h; echo ''; echo '===== Swap ====='; swapon --show 2>/dev/null || cat /proc/swaps; echo ''; echo '===== 磁盘 I/O 概况 ====='; iostat -x 1 1 2>/dev/null || echo 'iostat not available'; echo ''; echo '===== vmstat ====='; vmstat 1 3 2>/dev/null || echo 'vmstat not available'
```

## 第二步：CPU 排查

```bash
# Top CPU 进程
ssh_bash(server_id, "ps aux --sort=-%cpu | head -15")

# CPU 各核使用率
ssh_bash(server_id, "mpstat -P ALL 1 3 2>/dev/null || echo 'mpstat not available (install sysstat)'")

# 负载历史（sar）
ssh_bash(server_id, "sar -u 1 5 2>/dev/null || echo 'sar not available'")

# 指定进程的 CPU 使用
ssh_bash(server_id, "top -b -n 1 -p <PID> | tail -3")

# 进程的线程级 CPU 使用
ssh_bash(server_id, "top -b -n 1 -H -p <PID> | head -20")
```

## 第三步：内存排查

```bash
# Top 内存进程
ssh_bash(server_id, "ps aux --sort=-%mem | head -15")

# 详细内存信息
ssh_bash(server_id, "cat /proc/meminfo | head -30")

# 进程内存详情
ssh_bash(server_id, "cat /proc/<PID>/status | grep -E 'VmSize|VmRSS|VmSwap|Threads'")

# 内存使用按进程汇总（RSS）
ssh_bash(server_id, "ps -eo pid,rss,comm --sort=-rss | head -15 | awk '{printf \"%s\\t%s MB\\t%s\\n\", $1, $2/1024, $3}'")

# OOM Killer 记录
ssh_bash(server_id, "dmesg -T | grep -i 'oom\|killed process' | tail -10 2>/dev/null")
ssh_bash(server_id, "journalctl -k --grep='oom' --no-pager -n 10 2>/dev/null")

# Swap 使用按进程
ssh_bash(server_id, "for f in /proc/[0-9]*/status; do awk '/^(Name|VmSwap)/{printf $2\" \"}' $f 2>/dev/null && echo; done | sort -k2 -rn | head -10")
```

## 第四步：I/O 排查

```bash
# 磁盘 I/O 统计
ssh_bash(server_id, "iostat -xd 1 3 2>/dev/null || echo 'iostat not available'")

# I/O 按进程排序
ssh_bash(server_id, "iotop -b -n 1 --only 2>/dev/null || echo 'iotop not available'")

# 进程 I/O 统计
ssh_bash(server_id, "cat /proc/<PID>/io 2>/dev/null || echo 'permission denied or PID not found'")

# I/O wait 检查
ssh_bash(server_id, "vmstat 1 5 | awk 'NR>1{print \"wa=\"$16}' 2>/dev/null")
```

## 第五步：进程详细排查

### 文件描述符

```bash
# 系统级 FD 使用
ssh_bash(server_id, "cat /proc/sys/fs/file-nr")

# 进程 FD 使用
ssh_bash(server_id, "ls /proc/<PID>/fd 2>/dev/null | wc -l")

# 进程 FD 限制
ssh_bash(server_id, "cat /proc/<PID>/limits | grep 'Max open files'")

# 打开的文件列表
ssh_bash(server_id, "lsof -p <PID> | head -30 2>/dev/null || echo 'lsof not available'")
```

### 僵尸进程

```bash
# 查找僵尸进程
ssh_bash(server_id, "ps aux | awk '$8==\"Z\" {print}'")

# 僵尸进程的父进程
ssh_bash(server_id, "ps -eo pid,ppid,stat,comm | awk '$3~/Z/ {print}'")
```

### 进程跟踪

```bash
# 进程系统调用跟踪（限时限量）
ssh_bash(server_id, "timeout 5 strace -c -p <PID> 2>&1 || echo 'strace not available or permission denied'")

# 进程网络连接
ssh_bash(server_id, "ss -tnp | grep 'pid=<PID>' | head -20")

# 进程树
ssh_bash(server_id, "pstree -p <PID> 2>/dev/null || ps --forest -p <PID>")
```

## 常见问题排查

| 问题 | 排查命令/方式 |
|------|-------------|
| CPU 100% | `ps aux --sort=-%cpu` 定位进程 + `top -H -p PID` 查线程 + `strace` 跟踪 |
| 内存泄漏 | `ps aux --sort=-%mem` + 持续观察 RSS 增长 + `/proc/PID/smaps` |
| I/O wait 高 | `iostat -x` 定位磁盘 + `iotop` 定位进程 |
| 僵尸进程 | `ps aux \| awk '$8=="Z"'` + 找父进程 + 信号处理 |
| FD 耗尽 | `/proc/sys/fs/file-nr` + `/proc/PID/fd` 计数 + `lsof` 定位 |
| OOM Killer | `dmesg \| grep oom` + `/proc/PID/oom_score` + 内存限制检查 |
| 负载高但 CPU 不高 | 检查 I/O wait（vmstat wa 列）+ 不可中断进程（`ps aux \| awk '$8~/D/'`） |
| Swap 使用率高 | `free -h` + Swap 按进程排序 + 是否需要增加内存 |

## 注意事项

- **strace 谨慎使用**：`strace` 会降低被跟踪进程的性能，始终加 `timeout`
- **先只读后操作**：排查阶段不执行 `kill`、`renice` 等操作
- **数据采样**：vmstat/iostat/mpstat 建议采样多次（如 `vmstat 1 5`）看趋势
- **权限限制**：`/proc/<PID>/` 某些文件需要 root 权限
