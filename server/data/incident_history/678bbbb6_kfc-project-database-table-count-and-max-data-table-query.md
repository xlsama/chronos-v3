# 事件排查报告

## 事件概要
- **标题**: KFC 项目数据库表数量及最大数据量表查询
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
用户询问 KFC 项目下包含的数据库表总数，以及哪张表的数据量（行数）最大。这是一个关于系统元数据和实时数据统计的查询请求，而非故障排查。

## 排查过程
1.  **上下文收集与知识库检索**：
    *   调用 `list_projects` 确认项目 ID 为 `f0fef66d-7eb8-4269-b804-60e146009aa3` (kfc)。
    *   检索知识库和文档 (`README.md`)，初步确认系统包含 5 张数据表，并识别出 `daily_sales` 等表名。
    *   历史事件库无相关记录，确认为非历史故障。

2.  **服务器环境检查**：
    *   连接生产服务器 (`kfc 生产服务器`, IP: 192.168.107.3)。
    *   检查进程状态：未发现独立的 PostgreSQL 进程运行在本地，但确认 Node.js 服务 (PID 35) 正在监听端口 3001。
    *   检查网络端口：确认 3001 端口有 Node 进程监听，100 端口有 sshd 监听。
    *   检查 Docker：确认未使用 Docker 容器化部署。

3.  **代码与配置分析**：
    *   查看 `/app/package.json`，确认项目依赖 `drizzle-orm` 和 `postgres` 驱动。
    *   读取迁移文件 `/app/drizzle/0000_init.sql`，确认存在以下 5 张表的定义：`alerts`, `daily_sales`, `equipment`, `inspection_records`, `stores`。
    *   读取 `/app/dist/db/index.js`，获取数据库连接字符串默认值为 `postgres://kfc:kfc123@localhost:5433/kfc_monitor`。
    *   尝试直接通过 `psql` 连接本地 5433 端口失败（Connection refused），表明数据库可能位于远程或内部网络其他节点，但应用服务本身可访问 API。

4.  **API 数据验证与统计**：
    *   由于无法直接连接数据库执行 SQL 统计，转而通过应用提供的 REST API 接口获取各表数据量。
    *   依次调用以下接口并解析 JSON 响应以计算行数：
        *   `GET /api/stores` -> 返回 15 行
        *   `GET /api/alerts` -> 返回 29 行
        *   `GET /api/equipment` -> 返回 60 行
        *   `GET /api/sales` (对应 daily_sales) -> 返回 45 行
        *   `GET /api/inspections` (对应 inspection_records) -> 返回 20 行

5.  **结果汇总**：
    *   对比各表行数：stores(15), alerts(29), equipment(60), daily_sales(45), inspection_records(20)。
    *   确认数据量最大的表为 `equipment`。

## 根因分析
本次“事件”实为信息查询请求。
*   **表结构根因**：基于 `/app/drizzle/0000_init.sql` 和 `/app/dist/db/schema.js` 定义，KFC 项目架构设计包含 5 个核心业务实体表。
*   **数据量差异根因**：`equipment` 表数据量最大（60 行），是因为每个门店（共 15 家）下挂载了多台设备，导致该表记录数自然多于单店维度的销售、告警或检查记录表。

## 修复措施
本次操作为信息获取，无需修复操作。已输出最终统计结论：
1.  **表总数**：5 张。
2.  **具体表名**：`stores`, `equipment`, `alerts`, `inspection_records`, `daily_sales`。
3.  **数据量最大表**：`equipment` (设备表)，当前记录数为 60 行。