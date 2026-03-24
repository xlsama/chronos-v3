---
name: 网络排查
description: 网络连通性与性能排查指南。当事件涉及网络不通、连接超时、DNS 解析失败、延迟高、丢包、防火墙规则、端口不通、TCP 连接异常、带宽占满、路由问题、ARP 异常、网卡故障、MTU 问题、VPN 隧道、负载均衡健康检查失败时使用。
metadata:
  pattern: pipeline
  domain: network
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
3. 结合事件描述，确定源服务器、目标地址/端口和网络问题类型

## 第一步：基础连通性

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 网络接口 ====='; ip addr show 2>/dev/null || ifconfig; echo ''; echo '===== 路由表 ====='; ip route show 2>/dev/null || route -n; echo ''; echo '===== DNS 配置 ====='; cat /etc/resolv.conf; echo ''; echo '===== 主机名解析 ====='; hostname -I 2>/dev/null
```

### ICMP 连通性

```bash
ssh_bash(server_id, "ping -c 5 -W 3 <目标地址>")
```

### TCP 端口连通性

```bash
# telnet 方式
ssh_bash(server_id, "timeout 5 bash -c 'echo > /dev/tcp/<目标IP>/<端口>' 2>&1 && echo 'PORT OPEN' || echo 'PORT CLOSED/FILTERED'")

# curl 方式（HTTP/HTTPS）
ssh_bash(server_id, "curl -sS -o /dev/null -w 'HTTP %{http_code} | Time: %{time_total}s | Connect: %{time_connect}s\\n' --connect-timeout 5 http://<目标>:<端口>/ 2>&1")

# nc 方式
ssh_bash(server_id, "nc -zv -w 3 <目标IP> <端口> 2>&1")
```

## 第二步：DNS 排查

```bash
# DNS 解析
ssh_bash(server_id, "dig <域名> +short 2>/dev/null || nslookup <域名>")

# 指定 DNS 服务器查询
ssh_bash(server_id, "dig @8.8.8.8 <域名> +short 2>/dev/null")

# 完整 DNS 记录
ssh_bash(server_id, "dig <域名> ANY +noall +answer 2>/dev/null")

# 反向解析
ssh_bash(server_id, "dig -x <IP地址> +short 2>/dev/null")

# DNS 响应时间
ssh_bash(server_id, "dig <域名> | grep 'Query time' 2>/dev/null")
```

## 第三步：路由与延迟

```bash
# 路由追踪
ssh_bash(server_id, "traceroute -n -w 3 <目标地址> 2>/dev/null || tracepath <目标地址> 2>/dev/null")

# mtr（综合 ping + traceroute，持续检测）
ssh_bash(server_id, "mtr -n -r -c 10 <目标地址> 2>/dev/null || echo 'mtr not available'")
```

## 第四步：端口与连接状态

```bash
# 监听端口
ssh_bash(server_id, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")

# TCP 连接状态统计
ssh_bash(server_id, "ss -s 2>/dev/null")

# 连接状态分布（TIME_WAIT/ESTABLISHED/CLOSE_WAIT 等）
ssh_bash(server_id, "ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn")

# 指定端口的连接详情
ssh_bash(server_id, "ss -tnp | grep ':<端口>' | head -20")

# 大量 TIME_WAIT 检查
ssh_bash(server_id, "ss -tan state time-wait | wc -l")
```

### 防火墙规则

```bash
# iptables
ssh_bash(server_id, "iptables -L -n --line-numbers 2>/dev/null || echo 'iptables not available or no permission'")

# firewalld
ssh_bash(server_id, "firewall-cmd --list-all 2>/dev/null || echo 'firewalld not available'")

# ufw
ssh_bash(server_id, "ufw status verbose 2>/dev/null || echo 'ufw not available'")
```

## 第五步：带宽与流量

```bash
# 网络接口流量统计
ssh_bash(server_id, "cat /proc/net/dev | column -t")

# 实时流量（按进程）
ssh_bash(server_id, "nethogs -t -c 3 2>/dev/null || echo 'nethogs not available'")

# 实时流量（按接口）
ssh_bash(server_id, "iftop -t -s 5 -n 2>/dev/null || echo 'iftop not available'")

# 网卡错误统计
ssh_bash(server_id, "ip -s link show 2>/dev/null || netstat -i")
```

### 抓包分析（按需）

```bash
# 抓取特定端口的数据包（限制数量）
ssh_bash(server_id, "timeout 10 tcpdump -i any -nn -c 20 port <端口> 2>/dev/null || echo 'tcpdump not available or no permission'")

# 抓取与特定主机的通信
ssh_bash(server_id, "timeout 10 tcpdump -i any -nn -c 20 host <目标IP> 2>/dev/null")
```

## 常见问题排查

| 问题 | 排查命令/方式 |
|------|-------------|
| Connection refused | `ss -tlnp` 确认端口是否监听 + 服务状态检查 |
| Connection timed out | ping 连通性 + 防火墙规则 + 路由检查 |
| DNS NXDOMAIN | `dig @8.8.8.8` 对比本地 DNS + `/etc/resolv.conf` |
| 高延迟 | `mtr` 定位延迟节点 + 带宽检查 |
| 丢包 | `ping -c 100` 统计丢包率 + `mtr` 定位丢包节点 |
| TIME_WAIT 过多 | `ss -tan state time-wait \| wc -l` + 内核参数检查 |
| CLOSE_WAIT 堆积 | `ss -tnp state close-wait` 定位进程 + 应用连接释放检查 |
| 带宽满 | `/proc/net/dev` 流量统计 + `nethogs` 定位进程 |

## 注意事项

- **tcpdump 谨慎使用**：始终加 `-c`（限制包数）或 `timeout`，避免输出过多
- **先只读后操作**：排查阶段不修改防火墙规则、路由表
- **权限限制**：部分命令（tcpdump、iptables）需要 root 权限，注意错误提示
- **内网 vs 公网**：区分内网连通性和公网连通性问题，分别排查
