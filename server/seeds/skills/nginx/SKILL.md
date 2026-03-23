---
name: Nginx 排查
description: Nginx Web 服务器与反向代理排查指南。当事件涉及 Nginx 配置错误、502 Bad Gateway、504 Gateway Timeout、403 Forbidden、SSL 证书问题、上游服务不可达、请求超时、限流触发、负载均衡异常、Nginx 重载失败、访问日志分析、Worker 进程异常时使用。
metadata:
  pattern: pipeline
  domain: web
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
3. 结合事件描述，确定目标服务器和 Nginx 问题类型

## 第一步：Nginx 状态检查

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== Nginx 进程 ====='; ps aux | grep '[n]ginx' | head -10; echo ''; echo '===== Nginx 版本 ====='; nginx -v 2>&1; echo ''; echo '===== 配置语法检查 ====='; nginx -t 2>&1; echo ''; echo '===== systemd 状态 ====='; systemctl status nginx --no-pager 2>/dev/null || service nginx status 2>/dev/null; echo ''; echo '===== Worker 连接数 ====='; ss -tnp | grep nginx | wc -l
```

## 第二步：配置分析

```bash
# 完整生效配置（展开所有 include）
ssh_bash(server_id, "nginx -T 2>/dev/null | head -200")

# 主配置文件
ssh_bash(server_id, "cat /etc/nginx/nginx.conf")

# 站点配置列表
ssh_bash(server_id, "ls -la /etc/nginx/sites-enabled/ 2>/dev/null || ls -la /etc/nginx/conf.d/ 2>/dev/null")

# 查看特定站点配置
ssh_bash(server_id, "cat /etc/nginx/sites-enabled/<site>.conf 2>/dev/null || cat /etc/nginx/conf.d/<site>.conf 2>/dev/null")
```

### 关键配置项检查

```bash
# upstream 配置
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -A 5 'upstream'")

# worker 配置
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -E 'worker_processes|worker_connections'")

# 超时配置
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -E 'proxy_connect_timeout|proxy_read_timeout|proxy_send_timeout|client_body_timeout'")
```

## 第三步：日志分析

### 错误日志

```bash
# 最近错误日志
ssh_bash(server_id, "tail -50 /var/log/nginx/error.log 2>/dev/null || echo 'error log not found'")

# upstream 相关错误
ssh_bash(server_id, "grep -i 'upstream' /var/log/nginx/error.log | tail -20 2>/dev/null")

# 连接错误
ssh_bash(server_id, "grep -iE 'connect|refused|timeout|reset' /var/log/nginx/error.log | tail -20 2>/dev/null")
```

### 访问日志分析

```bash
# 最近请求
ssh_bash(server_id, "tail -20 /var/log/nginx/access.log 2>/dev/null")

# HTTP 状态码统计
ssh_bash(server_id, "awk '{print $9}' /var/log/nginx/access.log 2>/dev/null | sort | uniq -c | sort -rn | head -10")

# 5xx 错误请求
ssh_bash(server_id, "awk '$9 ~ /^5/' /var/log/nginx/access.log 2>/dev/null | tail -20")

# 4xx 错误请求
ssh_bash(server_id, "awk '$9 ~ /^4/' /var/log/nginx/access.log 2>/dev/null | tail -20")

# 慢请求（请求时间 > 5s，需要日志中有 request_time）
ssh_bash(server_id, "awk '{if($(NF) > 5) print}' /var/log/nginx/access.log 2>/dev/null | tail -10")

# Top IP
ssh_bash(server_id, "awk '{print $1}' /var/log/nginx/access.log 2>/dev/null | sort | uniq -c | sort -rn | head -10")
```

## 第四步：502/504 专项排查

### 502 Bad Gateway

```bash
# 1. 检查上游服务是否运行
ssh_bash(server_id, "ss -tlnp | grep '<upstream_port>'")

# 2. 测试上游服务连通性
ssh_bash(server_id, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<upstream_port>/ 2>&1")

# 3. 检查错误日志中的 upstream 错误
ssh_bash(server_id, "grep 'upstream' /var/log/nginx/error.log | tail -10")

# 4. 检查 SELinux 是否阻止（CentOS/RHEL）
ssh_bash(server_id, "getenforce 2>/dev/null; getsebool -a 2>/dev/null | grep httpd_can_network_connect")
```

### 504 Gateway Timeout

```bash
# 1. 检查超时配置
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -E 'proxy_.*timeout'")

# 2. 检查上游服务响应时间
ssh_bash(server_id, "curl -s -o /dev/null -w 'Total: %{time_total}s' http://127.0.0.1:<upstream_port>/ 2>&1")

# 3. 上游服务负载
ssh_bash(server_id, "ss -tnp | grep '<upstream_port>' | wc -l")
```

## 第五步：SSL 检查

```bash
# SSL 证书路径和配置
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -E 'ssl_certificate|ssl_protocols|ssl_ciphers'")

# 证书过期检查
ssh_bash(server_id, "openssl x509 -in <cert_path> -noout -dates 2>/dev/null")

# SSL 连接测试（从本地）
bash("openssl s_client -connect <域名>:443 -servername <域名> < /dev/null 2>/dev/null | openssl x509 -noout -dates")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 502 Bad Gateway | 上游服务状态 + `ss -tlnp` 确认端口监听 + 错误日志 upstream |
| 504 Gateway Timeout | `proxy_read_timeout` 配置 + 上游响应时间 + 上游负载 |
| 413 Request Entity Too Large | `client_max_body_size` 配置检查 |
| 403 Forbidden | 文件权限 + `autoindex` + `allow/deny` 规则 + SELinux |
| SSL 握手失败 | 证书路径 + 过期时间 + 协议/密码套件兼容性 |
| 配置重载失败 | `nginx -t` 语法检查 + 错误提示定位 |
| Worker 进程异常 | `ps aux \| grep nginx` + error.log + 系统资源检查 |
| 限流触发（429） | `limit_req_zone`/`limit_conn_zone` 配置检查 |

## 注意事项

- **先 `nginx -t` 再操作**：任何配置修改前先验证语法
- **先只读后操作**：排查阶段不执行 `nginx -s reload/stop`，需修复时告知用户
- **日志路径不固定**：通过 `nginx -T | grep log` 确认实际日志路径
- **Docker 中的 Nginx**：通过 `ssh_bash` + `docker exec` 执行，日志可能在容器内
