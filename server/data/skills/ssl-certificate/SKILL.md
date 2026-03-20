---
name: SSL/TLS 证书排查
description: SSL/TLS 证书排查指南。当事件涉及 HTTPS 证书过期、SSL 握手失败、证书链不完整、证书不匹配、TLS 版本问题、Let's Encrypt 续期失败、自签名证书、客户端证书验证、OCSP 装订、混合内容警告时使用。
metadata:
  pattern: pipeline
  domain: security
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
3. 结合事件描述，确定目标域名、服务器和证书问题类型

## 第一步：远程证书检查

### 从服务器端检查（通过 ssh_bash）

```bash
# 连接并查看证书信息
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -subject -issuer -dates -serial")

# 完整证书链
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -servername <域名> -showcerts 2>/dev/null | grep -E 's:|i:|depth'")

# 证书详情
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -text | head -40")

# SAN（Subject Alternative Names）
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -ext subjectAltName 2>/dev/null")
```

### 从本地检查（通过 bash）

```bash
# 远程证书过期时间检查
bash("echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | openssl x509 -noout -dates")

# 证书链验证
bash("echo | openssl s_client -connect <域名>:443 -servername <域名> 2>/dev/null | grep -E 'Verify return code'")
```

## 第二步：本地证书文件检查

```bash
# 查看证书文件详情
ssh_bash(server_id, "openssl x509 -in <cert_path> -noout -subject -issuer -dates -serial 2>/dev/null")

# 证书完整信息
ssh_bash(server_id, "openssl x509 -in <cert_path> -noout -text 2>/dev/null | head -40")

# 证书指纹
ssh_bash(server_id, "openssl x509 -in <cert_path> -noout -fingerprint -sha256 2>/dev/null")
```

### 证书与私钥匹配验证

```bash
# 证书 modulus
ssh_bash(server_id, "openssl x509 -in <cert_path> -noout -modulus 2>/dev/null | openssl md5")

# 私钥 modulus
ssh_bash(server_id, "openssl rsa -in <key_path> -noout -modulus 2>/dev/null | openssl md5")

# 两者 MD5 相同则匹配
```

### 证书链完整性

```bash
# 验证证书链
ssh_bash(server_id, "openssl verify -CAfile <ca_bundle_path> <cert_path> 2>/dev/null")

# 查看中间证书
ssh_bash(server_id, "openssl crl2pkcs7 -nocrl -certfile <cert_path> 2>/dev/null | openssl pkcs7 -print_certs -noout")
```

## 第三步：Web 服务器证书配置

### Nginx

```bash
ssh_bash(server_id, "nginx -T 2>/dev/null | grep -E 'ssl_certificate|ssl_protocols|ssl_ciphers|ssl_prefer_server_ciphers'")
```

### Apache

```bash
ssh_bash(server_id, "apachectl -S 2>/dev/null | head -20")
ssh_bash(server_id, "grep -rn 'SSLCertificate\|SSLProtocol' /etc/httpd/ /etc/apache2/ 2>/dev/null | head -10")
```

### 测试 TLS 协议版本

```bash
# 测试 TLS 1.2
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -tls1_2 2>/dev/null | head -5")

# 测试 TLS 1.3
ssh_bash(server_id, "echo | openssl s_client -connect <域名>:443 -tls1_3 2>/dev/null | head -5")
```

## 第四步：Let's Encrypt / Certbot

```bash
# Certbot 证书列表
ssh_bash(server_id, "certbot certificates 2>/dev/null || echo 'certbot not available'")

# 续期测试（dry-run）
ssh_bash(server_id, "certbot renew --dry-run 2>/dev/null | tail -10")

# Certbot 日志
ssh_bash(server_id, "tail -30 /var/log/letsencrypt/letsencrypt.log 2>/dev/null || echo 'no certbot log'")

# 证书自动续期定时任务
ssh_bash(server_id, "systemctl list-timers 2>/dev/null | grep certbot; crontab -l 2>/dev/null | grep certbot")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| 证书过期 | `openssl x509 -dates` 检查 notAfter + certbot renew |
| 证书链不完整 | `openssl s_client -showcerts` 检查中间证书 + `openssl verify -CAfile` |
| 域名不匹配 | `openssl x509 -noout -ext subjectAltName` 检查 SAN 列表 |
| SSL 握手失败 | 检查 TLS 版本兼容性 + 密码套件 + 证书链 |
| TLS 版本不兼容 | `openssl s_client -tls1_2/-tls1_3` 测试各版本 |
| Let's Encrypt 续期失败 | `certbot renew --dry-run` + 日志检查 + 端口 80/443 可达性 |
| 证书与私钥不匹配 | modulus MD5 对比 |
| 自签名证书不受信 | 检查 CA 证书是否添加到信任存储 |

## 注意事项

- **先只读后操作**：排查阶段不执行 `certbot renew`（不带 --dry-run）、证书替换等操作
- **私钥安全**：不要输出私钥内容到日志，仅检查 modulus
- **SNI 必须指定**：`openssl s_client` 需要 `-servername` 参数才能获取正确证书
- **端口非 443 场景**：部分服务使用非标准端口（如 8443），注意调整
