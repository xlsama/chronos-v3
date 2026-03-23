---
name: 安全审计
description: 安全审计与入侵排查指南。当事件涉及安全告警、异常登录、SSH 暴力破解、可疑进程、未授权访问、端口扫描、权限异常、恶意文件、rootkit 检测、防火墙规则审计、安全补丁、账户异常时使用。
metadata:
  pattern: pipeline
  domain: security
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
3. 结合事件描述，确定目标服务器和安全问题类型

## 第一步：登录审计

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 最近登录 ====='; last -20 2>/dev/null; echo ''; echo '===== 当前登录用户 ====='; who; echo ''; echo '===== 最后登录记录 ====='; lastlog 2>/dev/null | grep -v 'Never' | head -20; echo ''; echo '===== 失败登录 ====='; lastb 2>/dev/null | head -20 || echo 'lastb not available'
```

### SSH 暴力破解检测

```bash
# Debian/Ubuntu
ssh_bash(server_id, "grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -20")
ssh_bash(server_id, "grep 'Failed password' /var/log/auth.log 2>/dev/null | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head -10")

# CentOS/RHEL
ssh_bash(server_id, "grep 'Failed password' /var/log/secure 2>/dev/null | tail -20")

# journalctl
ssh_bash(server_id, "journalctl -u sshd --since '24 hours ago' --no-pager | grep -i 'failed\|invalid\|refused' | tail -20")

# fail2ban 状态
ssh_bash(server_id, "fail2ban-client status 2>/dev/null; fail2ban-client status sshd 2>/dev/null || echo 'fail2ban not available'")
```

## 第二步：进程审计

```bash
# 所有进程（关注异常用户、路径、高资源占用）
ssh_bash(server_id, "ps auxf | head -50")

# 可疑进程：从 /tmp、/dev/shm 等目录运行的
ssh_bash(server_id, "ls -la /proc/*/exe 2>/dev/null | grep -E '/tmp/|/dev/shm/|deleted' | head -20")

# 高 CPU 无名进程（可能是挖矿）
ssh_bash(server_id, "ps aux --sort=-%cpu | head -10")

# 隐藏进程检测（对比 ps 和 /proc）
ssh_bash(server_id, "ps_count=$(ps -e --no-headers | wc -l); proc_count=$(ls -d /proc/[0-9]* | wc -l); echo \"ps: $ps_count, /proc: $proc_count\"")
```

## 第三步：文件审计

```bash
# SUID/SGID 文件（可能被利用提权）
ssh_bash(server_id, "find / -xdev -type f \\( -perm -4000 -o -perm -2000 \\) -exec ls -la {} \\; 2>/dev/null | head -30")

# 最近 24 小时修改的文件（排除 proc/sys）
ssh_bash(server_id, "find / -xdev -type f -mtime -1 -not -path '/var/log/*' -not -path '/tmp/*' 2>/dev/null | head -30")

# /tmp 和 /dev/shm 可疑文件
ssh_bash(server_id, "ls -la /tmp/ /dev/shm/ 2>/dev/null | head -30")

# 可疑 crontab
ssh_bash(server_id, "for u in $(cut -d: -f1 /etc/passwd); do echo \"=== $u ===\"; crontab -u $u -l 2>/dev/null; done | head -50")

# /etc 下最近修改的配置
ssh_bash(server_id, "find /etc -type f -mtime -7 2>/dev/null | head -20")
```

## 第四步：网络审计

```bash
# 异常监听端口
ssh_bash(server_id, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")

# 异常外联连接
ssh_bash(server_id, "ss -tnp 2>/dev/null | grep ESTABLISHED | head -20")

# 非标准端口的监听
ssh_bash(server_id, "ss -tlnp 2>/dev/null | awk 'NR>1{print $4}' | sort -u")

# 防火墙规则
ssh_bash(server_id, "iptables -L -n --line-numbers 2>/dev/null | head -30 || echo 'no iptables permission'")
```

## 第五步：账户审计

```bash
# 所有用户（关注 UID 0 的非 root 用户）
ssh_bash(server_id, "awk -F: '($3 == 0) {print $1}' /etc/passwd")

# 可登录用户
ssh_bash(server_id, "grep -v '/nologin\\|/false' /etc/passwd | head -20")

# 空密码用户
ssh_bash(server_id, "awk -F: '($2 == \"\" || $2 == \"!\") {print $1}' /etc/shadow 2>/dev/null || echo 'no permission to read shadow'")

# sudoers
ssh_bash(server_id, "cat /etc/sudoers 2>/dev/null | grep -v '^#' | grep -v '^$' | head -20")
ssh_bash(server_id, "ls -la /etc/sudoers.d/ 2>/dev/null")

# 最近新增用户
ssh_bash(server_id, "grep ':x:' /etc/passwd | awk -F: '$3 >= 1000 {print $1, $3, $6, $7}'")

# SSH 授权密钥
ssh_bash(server_id, "for h in /root /home/*; do echo \"=== $h ===\"; cat $h/.ssh/authorized_keys 2>/dev/null | wc -l; done")
```

### 自动化工具（如已安装）

```bash
# rkhunter
ssh_bash(server_id, "rkhunter --check --skip-keypress --report-warnings-only 2>/dev/null || echo 'rkhunter not available'")

# chkrootkit
ssh_bash(server_id, "chkrootkit 2>/dev/null | grep 'INFECTED' || echo 'chkrootkit not available or clean'")

# lynis 审计
ssh_bash(server_id, "lynis audit system --quick --no-colors 2>/dev/null | tail -30 || echo 'lynis not available'")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| SSH 暴力破解 | auth.log/secure 失败记录 + fail2ban 状态 + 来源 IP 统计 |
| 挖矿进程 | `ps aux --sort=-%cpu` + 进程路径检查 + 外联连接（矿池端口） |
| Webshell | `find` 最近修改的 web 目录文件 + 可疑 PHP/JSP 内容 |
| 提权痕迹 | SUID/SGID 异常文件 + sudo 日志 + UID 0 非 root 账户 |
| 后门账户 | `/etc/passwd` 新增用户 + `authorized_keys` 异常公钥 |
| 异常端口 | `ss -tlnp` 未知监听 + 进程路径确认 |

## 注意事项

- **先只读后操作**：排查阶段不执行 kill、删除文件、修改权限等操作
- **证据保全**：发现入侵迹象时，记录但不清除，避免破坏取证
- **rkhunter/chkrootkit 结果**：可能有误报，需结合其他证据判断
- **敏感信息**：不要输出 /etc/shadow 完整内容、私钥等敏感数据
- **audit 日志**：如启用了 auditd，可通过 `ausearch` 查询更详细的操作记录
