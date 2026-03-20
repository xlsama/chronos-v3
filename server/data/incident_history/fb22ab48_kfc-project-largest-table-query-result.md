# 事件排查报告

## 事件概要
- **标题**: kfc 项目数据库最大数据表查询
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
用户询问 kfc 项目中数据量最大的数据库表是哪一张。该请求属于数据库元数据查询类问题，旨在获取各表当前的行数统计信息，而非故障排查。

## 排查过程
1. **上下文收集与知识库检索**：
   - 调用 `search_knowledge_base` 检索 kfc 项目相关文档及表结构信息。
   - 调用 `search_incident_history` 检索历史相似事件，确认无相关故障记录（因该问题为元数据查询）。
   - 检索结果显示项目涉及 `stores`、`daily_sales`、`inspection_records` 等表，但知识库中未包含各表的具体数据量统计。

2. **服务状态确认**：
   - 调用 `list_services` 确认 kfc 项目对应的数据库服务 `kfc-db` (PostgreSQL) 状态为 `online`，连接地址为 `localhost:5433`。

3. **执行数据库查询**：
   - 通过 `service_exec` 工具向 `kfc-db` 服务执行 SQL 语句，直接查询 PostgreSQL 系统视图 `pg_stat_user_tables`。
   - 查询语句：`SELECT schemaname, relname AS table_name, n_live_tup AS row_count FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;`

4. **结果分析**：
   - 获取到各表按活跃元组数 (`n_live_tup`) 降序排列的结果。
   - 识别出排名第一位的表为 `equipment`，行数为 60。

## 根因分析
- **知识盲区**：静态知识库（README.md）仅记录了表结构和部分业务查询示例，未维护实时的数据量统计信息，因此无法直接回答“哪张表数据最多”。
- **数据动态性**：数据库表行数随业务操作实时变化，必须通过连接数据库执行实时查询才能获取准确结论。
- **业务逻辑差异**：虽然根据业务常识推测 `daily_sales`（日销售表）可能数据量最大，但实际查询结果显示 `equipment` 表当前数据量最高，说明需以实际查询为准。

## 修复措施
- **执行操作**：通过运维工具直接连接 PostgreSQL 数据库，执行系统表查询命令获取最新统计数据。
- **验证结果**：
  - 成功获取 kfc 项目所有用户表的行数统计。
  - 确认数据量最多的表为 **`equipment`**（60 行），其次是 `daily_sales`（45 行）、`alerts`（29 行）等。
  - 将查询结果反馈给用户，问题得到圆满解决。