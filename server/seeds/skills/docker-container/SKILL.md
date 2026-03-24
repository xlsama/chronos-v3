---
name: Docker 容器排查
description: Docker 容器排查指南。当事件涉及 Docker 容器异常、容器重启、CrashLoop、OOM Kill、容器网络不通、端口映射失败、数据卷挂载异常、镜像拉取失败、容器日志、docker-compose、容器资源占用过高、容器进程异常时使用。
metadata:
  pattern: pipeline
  domain: container
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
3. 结合事件描述，确定目标服务器和相关容器

## 全局优先级（必须遵守）

- 当事件是”接口 pending / 端口监听但无响应 / 服务挂住 / 需要快速恢复”，并且目标机存在 Docker 迹象时，**先排查 Docker 容器层面，再深入应用进程层面**。
- `docker ps` 失败时，不要立刻说“没有容器”；要先区分：
  - `docker` 命令不在 PATH
  - Docker daemon 未启动
  - 当前用户无权限访问 Docker socket
- 首轮 Docker 探测必须保留原始 stderr，不要用 `2>/dev/null` 或把失败藏在管道后面。
- 如果错误明确是 `permission denied while trying to connect to the Docker daemon socket`，下一步应走审批后执行 `sudo docker ps` / `sudo docker ps -a` / `sudo docker logs`，而不是继续猜测“非容器部署”。
- 对大多数容器化业务，默认链路是：
  1. `docker ps`
  2. `docker ps -a`
  3. 找到承载故障端口的候选容器
  4. `docker logs --tail`
  5. 判断是否 OOM / hang / CrashLoop
  6. 必要时 `docker restart`

## 第一步：容器状态总览

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== Docker 命令路径 ====='; command -v docker 2>&1 || echo 'docker binary not found'; echo ''; echo '===== Docker 服务 ====='; systemctl status docker --no-pager 2>&1 | head -20 || echo 'systemctl not available'; echo ''; echo '===== Docker 版本 ====='; docker version --format '{{.Server.Version}}' 2>&1; echo ''; echo '===== 运行中容器 ====='; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1; echo ''; echo '===== 全部容器（含停止） ====='; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}' 2>&1; echo ''; echo '===== 容器资源使用 ====='; docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}' 2>&1
```

如果事件涉及某个业务端口，先用容器端口映射反查候选容器：

```bash
ssh_bash(server_id, "docker ps --format 'table {{.Names}}\t{{.Ports}}' 2>&1 | grep '<端口>'")
```

## 第二步：异常容器排查

### 容器日志

```bash
# 查看指定容器最近日志
ssh_bash(server_id, "docker logs --tail 100 --timestamps <容器名>")

# 查看指定时间段日志
ssh_bash(server_id, "docker logs --since '1h' <容器名>")
```

### 快速恢复（需要审批）

如果日志和状态已经证明容器只是挂住、且风险可接受，优先恢复动作是：

```bash
ssh_bash(server_id, "docker restart <容器名>")
```

### 容器详情

```bash
# 容器完整配置（启动参数、环境变量、挂载、网络等）
ssh_bash(server_id, "docker inspect <容器名>")

# 重启次数
ssh_bash(server_id, "docker inspect --format '{{.RestartCount}}' <容器名>")

# 退出码
ssh_bash(server_id, "docker inspect --format '{{.State.ExitCode}}' <容器名>")

# 健康检查状态
ssh_bash(server_id, "docker inspect --format '{{.State.Health.Status}}' <容器名> 2>/dev/null")
```

### 高重启次数容器

```bash
ssh_bash(server_id, "docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -i 'restarting'")
ssh_bash(server_id, "for c in $(docker ps -q); do name=$(docker inspect --format '{{.Name}}' $c); rc=$(docker inspect --format '{{.RestartCount}}' $c); [ \"$rc\" -gt 0 ] && echo \"$name restart=$rc\"; done")
```

## 第三步：网络排查

```bash
# Docker 网络列表
ssh_bash(server_id, "docker network ls")

# 查看特定网络详情（连接的容器、IP 分配）
ssh_bash(server_id, "docker network inspect <网络名>")

# 容器内网络连通性测试
ssh_bash(server_id, "docker exec <容器名> ping -c 2 <目标地址> 2>/dev/null || echo 'ping not available'")
ssh_bash(server_id, "docker exec <容器名> curl -sS -o /dev/null -w '%{http_code}\\n' http://<目标> 2>&1 || echo 'curl not available'")

# 端口映射检查
ssh_bash(server_id, "docker port <容器名>")
```

## 第四步：存储与资源

```bash
# Docker 磁盘使用概况
ssh_bash(server_id, "docker system df")

# 数据卷列表
ssh_bash(server_id, "docker volume ls")

# 悬空镜像和未使用卷
ssh_bash(server_id, "docker images --filter 'dangling=true' -q | wc -l")
ssh_bash(server_id, "docker volume ls --filter 'dangling=true' -q | wc -l")

# OOM Kill 检测
ssh_bash(server_id, "dmesg | grep -i 'oom' | tail -10 2>/dev/null || journalctl -k --grep='oom' --no-pager -n 10 2>/dev/null")

# 容器内存限制
ssh_bash(server_id, "docker inspect --format '{{.HostConfig.Memory}}' <容器名>")
```

## 第五步：docker-compose 场景

```bash
# compose 项目状态
ssh_bash(server_id, "cd <项目目录> && docker-compose ps 2>/dev/null || docker compose ps 2>/dev/null")

# compose 日志
ssh_bash(server_id, "cd <项目目录> && docker-compose logs --tail 50 <服务名> 2>/dev/null || docker compose logs --tail 50 <服务名> 2>/dev/null")

# compose 配置验证
ssh_bash(server_id, "cd <项目目录> && docker-compose config 2>/dev/null || docker compose config 2>/dev/null")
```

## 常见问题排查

| 问题 | 排查命令/方式 |
|------|-------------|
| 容器不断重启 | `docker inspect --format '{{.RestartCount}} {{.State.ExitCode}}'` + `docker logs --tail 50` |
| OOM Kill | `dmesg \| grep -i oom` + `docker inspect` 查内存限制 |
| 端口冲突 | `ss -tlnp \| grep <端口>` 确认端口占用 |
| DNS 解析失败 | `docker exec <容器> cat /etc/resolv.conf` + 网络模式检查 |
| 镜像拉取失败 | `docker pull <镜像>` 查看具体错误 + 检查 registry 连通性 |
| 磁盘占满 | `docker system df` + `df -h /var/lib/docker` |
| 容器内进程异常 | `docker exec <容器> ps aux` 或 `docker top <容器>` |
| 数据卷挂载异常 | `docker inspect` 查 Mounts 段 + 宿主机路径权限检查 |

## 注意事项

- **先只读后操作**：排查阶段不执行 `docker rm`、`docker stop` 等操作，需修复时明确告知用户
- **Docker 内的数据库/缓存**：如已注册为 service，优先用 `service_exec`；未注册则用 `ssh_bash` + `docker exec`
- **日志量控制**：始终使用 `--tail` 限制日志输出行数
- **compose v1 vs v2**：先尝试 `docker-compose`，不可用时降级到 `docker compose`
