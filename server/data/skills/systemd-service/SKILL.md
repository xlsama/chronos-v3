---
name: Systemd 服务排查
description: Systemd 服务与单元管理排查指南。当事件涉及服务启动失败、服务崩溃重启、systemctl 操作、服务依赖问题、cgroup 资源限制、systemd timer 定时任务、socket activation、服务超时、unit 文件配置错误、服务状态异常时使用。
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
3. 结合事件描述，确定目标服务器和问题服务名

## 第一步：服务状态检查

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 服务状态 ====='; systemctl status <service> --no-pager -l; echo ''; echo '===== 是否开机启用 ====='; systemctl is-enabled <service> 2>/dev/null; echo ''; echo '===== 服务进程 ====='; systemctl show <service> --property=MainPID,ExecMainPID,ExecMainStatus,ActiveState,SubState,Result --no-pager
```

### 服务完整属性

```bash
# 查看所有属性（启动命令、环境变量、资源限制等）
ssh_bash(server_id, "systemctl show <service> --no-pager")

# Unit 文件位置和内容
ssh_bash(server_id, "systemctl cat <service> 2>/dev/null")
```

## 第二步：服务日志

```bash
# 最近日志
ssh_bash(server_id, "journalctl -u <service> --no-pager -n 100")

# 按时间范围
ssh_bash(server_id, "journalctl -u <service> --since '1 hour ago' --no-pager | tail -100")

# 仅错误级别
ssh_bash(server_id, "journalctl -u <service> -p err --no-pager -n 50")

# 上次启动以来的日志
ssh_bash(server_id, "journalctl -u <service> -b --no-pager | tail -100")

# 实时追踪（限时）
ssh_bash(server_id, "timeout 10 journalctl -u <service> -f --no-pager 2>/dev/null")
```

## 第三步：启动失败排查

### 依赖链

```bash
# 服务依赖
ssh_bash(server_id, "systemctl list-dependencies <service> --no-pager")

# 反向依赖（谁依赖此服务）
ssh_bash(server_id, "systemctl list-dependencies <service> --reverse --no-pager")
```

### 启动命令验证

```bash
# 查看 ExecStart 命令
ssh_bash(server_id, "systemctl show <service> --property=ExecStart --no-pager")

# 验证可执行文件存在
ssh_bash(server_id, "systemctl cat <service> | grep ExecStart | awk -F'=' '{print $2}' | awk '{print $1}' | xargs ls -la 2>/dev/null")

# 环境变量
ssh_bash(server_id, "systemctl show <service> --property=Environment,EnvironmentFiles --no-pager")
```

### 资源限制（cgroup）

```bash
# 内存限制
ssh_bash(server_id, "systemctl show <service> --property=MemoryMax,MemoryCurrent --no-pager 2>/dev/null")

# CPU 限制
ssh_bash(server_id, "systemctl show <service> --property=CPUQuota,CPUWeight --no-pager 2>/dev/null")

# 任务数限制
ssh_bash(server_id, "systemctl show <service> --property=TasksMax,TasksCurrent --no-pager 2>/dev/null")

# 文件描述符限制
ssh_bash(server_id, "systemctl show <service> --property=LimitNOFILE --no-pager 2>/dev/null")
```

## 第四步：Timer 与其他单元类型

### Systemd Timer

```bash
# 所有定时器
ssh_bash(server_id, "systemctl list-timers --all --no-pager")

# 特定 Timer 状态
ssh_bash(server_id, "systemctl status <timer-name>.timer --no-pager")

# Timer 配置
ssh_bash(server_id, "systemctl cat <timer-name>.timer 2>/dev/null")

# 对应 Service 的日志
ssh_bash(server_id, "journalctl -u <timer-name>.service --since '24 hours ago' --no-pager | tail -30")
```

### 失败的单元

```bash
# 列出所有失败的单元
ssh_bash(server_id, "systemctl --failed --no-pager")

# 重置失败状态（排查后）
# ssh_bash(server_id, "systemctl reset-failed <service>")  # 需确认后执行
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 启动失败（exit-code） | `systemctl status` 查退出码 + `journalctl -u` 查日志 + ExecStart 路径验证 |
| 启动超时 | `systemctl show --property=TimeoutStartSec` + 日志定位卡在哪步 |
| 服务不断重启 | `systemctl show --property=NRestarts` + `Restart=` 配置 + 日志查崩溃原因 |
| 依赖未满足 | `list-dependencies` + 检查依赖服务状态 |
| OOM Kill（cgroup） | `MemoryMax` 设置 vs `MemoryCurrent` + journalctl 查 OOM 记录 |
| 权限不足 | `User=/Group=` 配置 + 文件权限 + SELinux/AppArmor |
| Unit 文件语法错误 | `systemd-analyze verify <service>` |
| 环境变量缺失 | `EnvironmentFile=` 路径是否存在 + 文件内容检查 |

## 注意事项

- **先只读后操作**：排查阶段不执行 `systemctl start/stop/restart`，需操作时告知用户
- **Unit 文件修改**：修改后需 `systemctl daemon-reload`，但排查阶段不要执行
- **Override 配置**：`/etc/systemd/system/<service>.d/override.conf` 可能覆盖默认配置
- **journalctl 持久化**：确认 `/var/log/journal/` 是否存在，否则日志重启后丢失
