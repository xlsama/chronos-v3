#!/bin/bash123
# MySQL 内存使用分析脚本
echo "=== 系统内存 ==="
free -m

echo ""
echo "=== MySQL 全局内存配置 ==="
mysql -e "
SELECT
  @@innodb_buffer_pool_size / 1024 / 1024 AS buffer_pool_mb,
  @@key_buffer_size / 1024 / 1024 AS key_buffer_mb,
  @@tmp_table_size / 1024 / 1024 AS tmp_table_mb,
  @@max_connections AS max_connections,
  @@sort_buffer_size / 1024 AS sort_buffer_kb,
  @@read_buffer_size / 1024 AS read_buffer_kb,
  @@join_buffer_size / 1024 AS join_buffer_kb;
"

echo ""
echo "=== 当前连接数 ==="
mysql -e "SHOW STATUS LIKE 'Threads_connected';"

echo ""
echo "=== 估算 per-thread 内存 ==="
mysql -e "
SELECT
  (@@sort_buffer_size + @@read_buffer_size + @@join_buffer_size + @@thread_stack) / 1024 / 1024 AS per_thread_mb;
"
