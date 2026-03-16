# Nginx 502 Bad Gateway — 上游服务崩溃

## 事件概述
用户反馈网站返回 502 Bad Gateway 错误，影响所有页面。持续约 10 分钟。

## 根因分析
- Nginx 日志显示 `connect() failed: Connection refused` 连接上游服务失败
- 上游 Node.js 应用因未捕获异常崩溃
- PM2 自动重启失败，因端口被残留进程占用

## 处理步骤
1. `curl -I localhost` 确认 502 状态
2. `tail -50 /var/log/nginx/error.log` 查看错误日志
3. `systemctl status node-app` 确认上游服务状态
4. `lsof -i :3000` 找到占用端口的残留进程
5. `kill -9 <pid>` 终止残留进程
6. `systemctl restart node-app` 重启应用服务

## 修复结果
服务恢复正常，502 错误消失。后续需修复 Node.js 应用中的异常处理。

## 标签
Nginx, 502, Node.js, 上游服务, 端口占用
