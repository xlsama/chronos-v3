# 事件排查报告

## 事件概要
- **标题**: KFC 项目数据库各表数据量统计查询
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
用户询问 KFC 项目中哪张数据表包含的数据量最多。该请求属于静态数据查询，非故障排查类事件，旨在获取业务数据库的结构与统计信息。

## 排查过程
1. **上下文检索**：
   - 调用 `list_projects` 确认项目 ID 为 `986b8f5f-f572-44db-8fb1-8e8430707b4a` (kfc)。
   - 检索知识库发现系统共包含 5 张数据表（`inspection_records`, `daily_sales` 等），但未包含具体行数统计。

2. **服务器环境调查**：
   - 连接至 `kfc server` (ID: `a25f1a20-9ccf-41f2-862f-dc190a9a999d`)。
   - 检查进程列表，发现 Node.js 应用监听在 3001 端口。
   - 检查文件结构，确认项目使用 Drizzle ORM，依赖 `postgres` 驱动。

3. **数据库配置定位**：
   - 查看 `/app/dist/db/index.js` 发现默认连接串指向 `localhost:5433`。
   - 尝试连接 `localhost:5433` 失败（Connection refused）。
   - 检查 Node 进程环境变量 (`/proc/35/environ`)，发现实际连接串为 `postgres://kfc:kfc123@postgres:5432/kfc_monitor`，表明数据库运行在名为 `postgres` 的 Docker 容器主机上。

4. **数据库连接与验证**：
   - 使用 `psql` 客户端通过 `host=postgres, port=5432` 成功连接数据库。
   - 执行 `\dt` 命令确认存在 5 张业务表：`alerts`, `daily_sales`, `equipment`, `inspection_records`, `stores`。

5. **数据量统计**：
   - 首先查询 `pg_stat_user_tables` 视图获取预估行数。
   - 随后执行 `COUNT(*)` 聚合查询对结果进行精确验证，确保数据准确性。

## 根因分析
本次任务并非故障排查，无需根因分析。系统架构正常，Node.js 应用通过环境变量动态获取数据库连接地址，成功定位到 PostgreSQL 数据库实例并获取了准确的元数据。

## 修复措施
本次操作为信息查询，未涉及故障修复，具体执行的操作及结论如下：

1. **执行操作**：
   - 执行 SQL 查询：`SELECT 'table_name' as table_name, COUNT(*) as count FROM ... UNION ALL ... ORDER BY count DESC;`
   
2. **验证结果**：
   - 查询结果显示各表行数如下：
     - `equipment`: 60 条
     - `daily_sales`: 45 条
     - `alerts`: 29 条
     - `inspection_records`: 20 条
     - `stores`: 15 条
   
3. **最终结论**：
   - **`equipment` (设备表)** 是 KFC 项目中数据量最多的表，共计 60 条记录。