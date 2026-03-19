# MySQL 内存分析指南123

## MySQL 内存分配模型

MySQL 内存消耗 = 全局缓冲区 + (每连接缓冲区 × 活跃连接数)

### 全局缓冲区（固定占用）
- `innodb_buffer_pool_size`: 最大内存消耗者，建议不超过物理内存的 60-70%
- `key_buffer_size`: MyISAM 索引缓存
- `query_cache_size`: 查询缓存（MySQL 8.0 已移除）

### 每连接缓冲区（动态分配）
- `sort_buffer_size`: 排序缓冲，默认 256KB
- `read_buffer_size`: 顺序读缓冲，默认 128KB
- `join_buffer_size`: 连接缓冲，默认 256KB
- `thread_stack`: 线程栈，默认 256KB

## 常见 OOM 场景

### 场景 1: buffer_pool 过大
- 症状: 启动后内存立即占满
- 排查: `SHOW VARIABLES LIKE 'innodb_buffer_pool_size'` vs `free -m`
- 修复: 调整 `innodb_buffer_pool_size` 到物理内存的 50-60%

### 场景 2: 连接数暴涨
- 症状: 内存缓慢增长后 OOM
- 排查: `SHOW STATUS LIKE 'Threads_connected'` 对比 `max_connections`
- 修复: 降低 `max_connections`，排查连接泄漏

### 场景 3: 大型临时表
- 症状: 某些慢查询执行期间内存飙升
- 排查: `SHOW STATUS LIKE 'Created_tmp_disk_tables'`
- 修复: 优化查询，调整 `tmp_table_size` 和 `max_heap_table_size`
