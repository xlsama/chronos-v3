# 进程因 OOM 被 Kill — Java 应用内存泄漏

## 事件概述
生产环境 Java 应用进程被 OOM Killer 终止，服务完全不可用，持续约 15 分钟。

## 根因分析
- dmesg 显示 `Out of memory: Kill process` 日志
- Java 应用 -Xmx 设置为 2GB，但容器内存限制为 2GB，未预留系统开销
- 应用存在缓存未设置上限，导致堆内存持续增长

## 处理步骤
1. `dmesg -T | grep -i oom` 确认 OOM 事件
2. `systemctl status app.service` 确认服务状态
3. `systemctl restart app.service` 重启应用
4. 修改 JVM 参数：`-Xmx1536m`，容器内存限制调整为 3GB

## 修复结果
服务恢复正常。调整 JVM 参数后内存使用稳定在 70% 以下。后续需排查缓存泄漏。

## 标签
OOM, 内存, Java, JVM, 容器
