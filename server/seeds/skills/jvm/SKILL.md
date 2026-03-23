---
name: JVM 应用排查
description: JVM 应用排查指南，适用于 Java/Kotlin/Scala 应用。当事件涉及 Java 应用异常、OutOfMemoryError、堆内存溢出、GC 停顿、线程死锁、CPU 飙高的 Java 进程、类加载异常、连接池泄漏、JVM 参数调优、Full GC 频繁、线程数过多时使用。
metadata:
  pattern: pipeline
  domain: application
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
3. 结合事件描述，确定目标服务器和 Java 应用进程

## 第一步：JVM 进程发现

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== Java 进程 ====='; jps -v 2>/dev/null || ps aux | grep '[j]ava' | head -10; echo ''; echo '===== JVM 版本 ====='; java -version 2>&1 | head -3; echo ''; echo '===== 进程资源占用 ====='; ps -eo pid,user,%cpu,%mem,rss,comm | grep java | head -10
```

### 提取 JVM 参数

```bash
# 完整 JVM 启动参数
ssh_bash(server_id, "jps -v 2>/dev/null | grep <关键字>")

# 或从 /proc 获取
ssh_bash(server_id, "cat /proc/<PID>/cmdline | tr '\\0' ' ' | fold -w 120")
```

## 第二步：线程分析

### 线程 Dump

```bash
# 生成线程 Dump
ssh_bash(server_id, "jstack <PID> 2>/dev/null | head -200")

# 检测死锁
ssh_bash(server_id, "jstack <PID> 2>/dev/null | grep -A 5 'Found.*deadlock'")

# 线程状态统计
ssh_bash(server_id, "jstack <PID> 2>/dev/null | grep 'java.lang.Thread.State' | sort | uniq -c | sort -rn")
```

### CPU 飙高线程定位

```bash
# 1. 找到高 CPU 的线程（OS 级别）
ssh_bash(server_id, "top -b -n 1 -H -p <PID> | head -20")

# 2. 将线程 ID 转为十六进制（用于匹配 jstack 中的 nid）
ssh_bash(server_id, "printf '%x\\n' <THREAD_ID>")

# 3. 在 jstack 中搜索该线程
ssh_bash(server_id, "jstack <PID> 2>/dev/null | grep -A 20 'nid=0x<HEX_TID>'")
```

### 线程数检查

```bash
ssh_bash(server_id, "cat /proc/<PID>/status | grep Threads")
ssh_bash(server_id, "jstack <PID> 2>/dev/null | grep 'java.lang.Thread.State' | wc -l")
```

## 第三步：内存分析

### 堆内存概况

```bash
# 堆内存使用情况
ssh_bash(server_id, "jmap -heap <PID> 2>/dev/null || echo 'jmap not available or permission denied'")

# 对象直方图（按大小排序，无需 heap dump）
ssh_bash(server_id, "jmap -histo <PID> 2>/dev/null | head -30")

# 只看活跃对象
ssh_bash(server_id, "jmap -histo:live <PID> 2>/dev/null | head -30")
```

### GC 统计

```bash
# GC 统计（每秒采样，共 5 次）
ssh_bash(server_id, "jstat -gc <PID> 1000 5 2>/dev/null || echo 'jstat not available'")

# GC 原因
ssh_bash(server_id, "jstat -gccause <PID> 1000 3 2>/dev/null")

# GC 容量
ssh_bash(server_id, "jstat -gccapacity <PID> 2>/dev/null")
```

### GC 日志分析

```bash
# 定位 GC 日志文件
ssh_bash(server_id, "jps -v 2>/dev/null | grep -oP '(-Xlog:gc[^ ]*|-XX:GCLogFileSize[^ ]*|-Xloggc:[^ ]*)' | head -5")

# 查看最近 GC 日志
ssh_bash(server_id, "tail -50 <gc_log_path> 2>/dev/null || echo 'GC log not found'")

# Full GC 频率
ssh_bash(server_id, "grep -c 'Full GC\\|Pause Full' <gc_log_path> 2>/dev/null || echo 'no Full GC log'")
```

## 第四步：其他排查

### 类加载

```bash
ssh_bash(server_id, "jstat -class <PID> 2>/dev/null")
```

### JMX 端口检查

```bash
ssh_bash(server_id, "jps -v 2>/dev/null | grep -oP 'jmxremote\\.port=\\K[0-9]+'")
```

### 应用日志

```bash
# 常见 Java 应用日志路径
ssh_bash(server_id, "find /var/log /opt /home -name '*.log' -path '*<应用名>*' -mmin -60 2>/dev/null | head -10")

# 查找 OOM 错误
ssh_bash(server_id, "grep -rn 'OutOfMemoryError\\|heap space\\|Metaspace' /var/log/<应用>/ 2>/dev/null | tail -10")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| OOM: Java heap space | `jmap -heap` 查堆使用率 + `jmap -histo` 查大对象 + `-Xmx` 配置 |
| OOM: Metaspace | `jstat -gc` 查 MC/MU + `-XX:MaxMetaspaceSize` 配置 + 类加载数 |
| 线程死锁 | `jstack` + 搜索 "Found deadlock" |
| GC overhead limit | `jstat -gc` 查 GC 频率和耗时 + 堆内存是否过小 |
| CPU 飙高 | `top -H -p PID` 找高 CPU 线程 → 转十六进制 → `jstack` 匹配 |
| Full GC 频繁 | GC 日志分析 + `jstat -gc` 关注 FGC/FGCT + 老年代使用率 |
| 连接池泄漏 | `jstack` 查连接相关线程状态 + 应用日志查 "pool exhausted" |
| 线程数过多 | `/proc/PID/status` Threads + `jstack` 分析线程来源 |

## 注意事项

- **jmap -histo:live 会触发 Full GC**：生产环境慎用，优先用 `jmap -histo`（不加 :live）
- **Heap Dump 谨慎**：`jmap -dump` 会暂停应用，大堆时间较长，不要在排查阶段执行
- **权限匹配**：jstack/jmap 需要与目标 Java 进程同用户或 root 执行
- **先只读后操作**：排查阶段不执行 kill、重启等操作
- **Docker 中的 JVM**：通过 `ssh_bash` + `docker exec` 执行，需确认容器内有 JDK 工具
