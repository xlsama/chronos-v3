# 事件排查报告

## 事件概要
- 标题：KFC 系统数据库表结构及数据量查询请求
- 严重程度：P3
- 处理状态：已解决

## 问题描述
用户需要获取 KFC 系统的数据库详细架构信息，具体包括：
1. 系统包含哪些数据库表。
2. 每张表的当前数据量（行数）。
受影响服务为 KFC 监控系统数据库（项目 ID: b08b7292-4af9-47de-b893-b2b79896b4ed），初始阶段无法直接通过文档或远程连接获取实时数据。

## 排查过程
按时间顺序记录的关键排查步骤和发现如下：

1.  **上下文检索**
    *   调用 `list_projects` 确认项目存在。
    *   检索历史事件库与知识库（KB），得知系统共包含 5 张数据表，使用 PostgreSQL，但缺乏具体的表名及实时数据量信息。
    *   初步获取连接命令：`psql -h localhost -p 5433 -U kfc -d kfc_monitor`。

2.  **本地连通性测试**
    *   执行命令 `psql -h localhost -p 5433 ...`，连接被拒绝（Connection refused）。
    *   检查宿主机状态：
        *   `docker ps` 显示未安装 Docker 环境。
        *   `netstat` 和 `ss` 均探测不到 5433 或 postgres 端口监听。
        *   `ps aux | grep postgres` 确认宿主机无 Postgres 进程运行。

3.  **容器内网络与配置分析**
    *   检查 `/etc/hosts` 与 `/app` 目录结构。
    *   查看 `entrypoint.sh` 启动脚本，确认应用内部依赖名为 `postgres` 的主机名进行连接，且等待其就绪后执行初始化。
    *   推断实际数据库服务存在于容器网络环境中，而非宿主机本地端口。

4.  **执行真实查询**
    *   切换连接目标至容器内部域名，执行命令：`PGPASSWORD=kfc123 psql -h postgres -U kfc -d kfc_monitor ...`。
    *   列出所有表：`SELECT tablename FROM pg_tables WHERE schemaname = 'public';`。
    *   统计各行数并获取表结构定义。

## 根因分析
本次操作虽为用户咨询而非故障报错，但在排查初期遇到以下阻塞点：
1.  **连接拓扑限制**：数据库服务并非运行在宿主机 `localhost`，而是位于容器网络中的 `postgres` 节点，导致直接使用宿主机地址连接失败。
2.  **信息缺失**：现有知识库仅记录了逻辑上的表数量（5 张），未包含实时的 DDL 定义和数据行计数，必须通过直连数据库执行查询获取最新状态。

## 修复措施
执行的修复操作及验证结果如下：

1.  **建立正确连接**
    *   修正连接参数，使用主机名 `postgres` 及默认端口，密码 `kfc123`。
    *   命令示例：`psql -h postgres -U kfc -d kfc_monitor`。

2.  **数据提取与验证**
    *   查询表列表，确认 5 张表名：`stores`, `equipment`, `daily_sales`, `inspection_records`, `alerts`。
    *   执行聚合查询获取数据量：
        | 表名 | 数据行数 |
        | :--- | :--- |
        | stores | 15 |
        | equipment | 60 |
        | daily_sales | 45 |
        | inspection_records | 20 |
        | alerts | 29 |
    *   验证核心表结构，确认 `stores` 表为主表，其他表通过外键关联。

3.  **结果确认**
    *   向用户输出完整的表结构清单及数据量统计。
    *   用户确认接收信息（Input: `confirmed`）。