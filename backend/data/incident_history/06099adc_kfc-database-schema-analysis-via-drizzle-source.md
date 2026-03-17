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

## 排查过程
| 序号 | 时间顺序 | 操作步骤 | 结果 |
|:---:|:---:|:---|:---|
| 1 | 第1步 | 查询可用数据库 (`SHOW DATABASES`) | PostgreSQL 客户端存在，但未找到活跃连接 |
| 2 | 第2步 | 查找 KFC 相关配置文件 (`.md`, `.sql`, `.yml`) | 未找到直接相关的配置文件 |
| 3 | 第3步 | 查看项目目录结构 (`/root/`, `/home/`, `/opt/`) | 发现 Node.js 项目存在于 `/app/` 目录 |
| 4 | 第4步 | 检查数据库客户端安装情况 (`which`, `dpkg -l`) | PostgreSQL Client 15 已安装 |
| 5 | 第5步 | 尝试列出 PostgreSQL 数据库 (`psql -l`) | 连接失败（权限/配置问题，但不影响 schema 查询） |
| 6 | 第6步 | 搜索 SQLite 数据库文件 | 未找到相关数据库文件 |
| 7 | 第7步 | 搜索 SQL/Migration/Schema 相关文件 | 找到 `/app/src/db/schema.ts` |
| 8 | 第8步 | 读取 Schema 定义文件 | **成功**，获取完整表结构定义 |

## 根因分析
本次为**信息梳理任务**而非故障排查，无需根因分析。

关键发现：
- KFC 项目使用 **PostgreSQL** 作为数据存储
- 数据库表结构通过 **Drizzle ORM** 在 TypeScript 文件中定义
- 所有表定义位于 `/app/src/db/schema.ts` 单文件中

## 修复措施
| 步骤 | 操作内容 | 验证结果 |
|:---:|:---|:---|
| 1 | 读取 `/app/src/db/schema.ts` Schema 定义文件 | ✅ 成功解析，提取出完整的表结构信息 |
| 2 | 汇总输出数据库表清单及关系说明 | ✅ 完成，提供给用户参考 |

## 补充说明
### 数据库表清单
| 表名 | 中文名 | 核心字段 | 关联关系 |
|:---|:---|:---|:---|
| stores | 门店表 | code, name, address, city | 核心主表，其他表外键关联 |
| equipment | 设备表 | store_id, name, type | → stores(storeId) |
| alerts | 告警表 | store_id, device_id, level | → stores(storeId) |
| inspection_records | 巡检记录表 | store_id, inspector, score | → stores(storeId) |
| daily_sales | 日销售表 | store_id, date, revenue | → stores(storeId) |

> 注：本次操作仅为信息收集，未对生产环境做任何修改。