---
name: MySQL OOM 排查
description: MySQL 进程被 OOM Killer 终止时的排查流程。dmesg 出现 killed process mysqld 时使用。
metadata:
  pattern: pipeline
  domain: mysql
  steps: "4"
---

按以下步骤严格顺序执行。每步完成后总结发现，再进入下一步。

## Step 1 — 确认 OOM 事件

执行以下命令确认 OOM:

```bash
dmesg | grep -i "oom\|killed process" | tail -20
journalctl -k | grep -i oom | tail -20
```

判断标准: 如果看到 "Out of memory: Killed process xxx (mysqld)"，确认是 OOM，继续下一步。如果不是 OOM，告知用户不适用此技能。

## Step 2 — 分析内存配置

```bash
mysql -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"
mysql -e "SHOW VARIABLES LIKE 'max_connections';"
free -m
cat /proc/meminfo | head -5
```

关注:
- `innodb_buffer_pool_size` 是否超过物理内存的 70%
- `max_connections` 是否过高（每个连接约占 10-50MB）

执行 `scripts/check_memory.sh` 获取内存分布快照。

## Step 3 — 排查内存消耗源

```bash
mysql -e "SHOW PROCESSLIST;" | head -30
mysql -e "SELECT * FROM performance_schema.memory_summary_global_by_event_name ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC LIMIT 10;"
```

参考 `references/memory-analysis.md` 了解详细分析方法。

## Step 4 — 给出结论和建议

基于以上数据，总结:
1. OOM 根因（buffer_pool 过大 / 连接数过多 / 临时表过大）
2. 具体调整建议和命令
3. 是否需要重启 MySQL
