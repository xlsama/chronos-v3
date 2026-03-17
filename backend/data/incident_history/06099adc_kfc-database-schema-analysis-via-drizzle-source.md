## 已有报告

# 事件排查报告

## 事件概要
- **标题**: KFC 项目数据库结构信息梳理
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
用户需要查询 KFC 项目的数据库表结构信息。经排查，服务器环境信息如下：
- **数据库类型**: PostgreSQL（已安装客户端）
- **项目路径**: `/app/src/`
- **ORM 框架**: Drizzle ORM
- **影响范围**: 仅涉及元数据查询，无业务服务受影响
- **用户需求细化**: 除表结构外，需确认核心存储表及业务数据（如销售、设备、告警）与主表的关联方式。

## 排查过程
| 序号 | 时间顺序 | 操作步骤 | 结果 |
|:---:|:---:|:---|:---|
| 1 | 第 1 步 | 尝试直连数据库查询表列表 (`psql -U postgres -d kfc -c "\\dt"`) | 初始报错 `Invalid server_id 'root@localhost:2222'`；后续调用 `list_servers` 接口获取有效服务器 ID `c9cd2e76-581b-40e4-8fd2-f6c47758643a` |
| 2 | 第 2 步 | 查找 KFC 相关配置文件 (`.md`, `.sql`, `.yml`) | 未找到直接相关的配置文件 |
| 3 | 第 3 步 | 查看项目目录结构 (`/root/`, `/home/`, `/opt/`) | 发现 Node.js 项目存在于 `/app/` 目录 |
| 4 | 第 4 步 | 检查数据库客户端安装情况 (`which`, `dpkg -l`) | PostgreSQL Client 15 已安装 |
| 5 | 第 5 步 | 验证数据库连接状态 | 使用正确 ID 再次连接时，报错 `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: No such file or directory`，确认无法通过本地 Socket 连接 PostgreSQL 服务 |
| 6 | 第 6 步 | 搜索 SQLite 数据库文件 | 未找到相关数据库文件 |
| 7 | 第 7 步 | 搜索 SQL/Migration/Schema 相关文件 | 找到 `/app/src/db/schema.ts` |
| 8 | 第 8 步 | 读取并分析 Schema 定义文件 | **成功**，根据 `drizzle-orm/pg-core` 配置分析表结构，确认基于显式外键的关联关系 |

## 根因分析
本次为**信息梳理任务**而非故障排查，无需根因分析。

关键发现：
- KFC 项目使用 **PostgreSQL** 作为数据存储
- 数据库表结构通过 **Drizzle ORM** 在 TypeScript 文件中定义
- 所有表定义位于 `/app/src/db/schema.ts` 单文件中
- **连接环境限制**：生产环境数据库服务未在本地监听指定 Socket 路径，导致无法直接执行 SQL 查询，最终通过静态代码分析达到目的
- **架构模式**：`stores` 为核心主表，采用 `drizzle-orm/pg-core` 显式外键约束构建的关系映射，确保了一对多（1:N）的数据一致性，不存在无明确外键的隐式关联

## 修复措施
| 步骤 | 操作内容 | 验证结果 |
|:---:|:---|:---|
| 1 | 读取 `/app/src/db/schema.ts` Schema 定义文件 | ✅ 成功解析，提取出完整的表结构信息 |
| 2 | 汇总输出数据库表清单及关系说明 | ✅ 完成，提供给用户参考 |
| 3 | **提供跨表关联查询的 SQL 示例** | ✅ 完成，供开发人员按地区查询门店销售情况等场景参考 |

## 补充说明
### 数据库表清单
| 表名 | 中文名 | 核心字段 | 关联关系 |
|:---|:---|:---|:---|
| stores | 门店表 | id, code, name, address, city | 核心主表，其他表外键关联 |
| equipment | 设备表 | store_id, name, type | → stores(storeId) |
| alerts | 告警表 | store_id, device_id, level | → stores(storeId) |
| inspection_records | 巡检记录表 | store_id, inspector, score | → stores(storeId) |
| daily_sales | 日销售表 | store_id, date, revenue | → stores(storeId) |

> 注：本次操作仅为信息收集，未对生产环境做任何修改。