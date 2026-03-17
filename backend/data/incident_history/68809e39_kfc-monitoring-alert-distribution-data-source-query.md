# 事件排查报告

## 事件概要
- **标题**: 告警分布图表数据源定位
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
- **受影响服务**: KFC 监控系统 Dashboard 页面
- **症状**: 用户询问告警分布图表查询的是哪张数据库表
- **影响范围**: 单条查询请求，不涉及系统异常或数据错误

## 排查过程
按时间顺序列出关键排查步骤和发现：

1. **初始询问**: 用户询问"这个这个是查的哪张表？"，信息不够完整
2. **补充信息**: 用户明确说明是"截图中的这个告警分布这个图表查的是哪张数据库"
3. **服务器识别**: 调用 `list_servers()` 确认生产服务器为 KFC 生产服务器 (ID: 2e42b350-52a0-4379-a227-b547a4204b8e)
4. **项目目录探查**: 
   - 执行 `find` 命令搜索代码文件
   - 确认项目根目录在 `/app/`
5. **源代码分析**: 
   - 进入 `/app/src/db/` 目录，查看数据库 schema 定义 (`schema.ts`)
   - 确认数据库类型为 PostgreSQL，连接地址 `localhost:5433`，数据库名 `kfc_monitor`
6. **路由层追踪**:
   - 通过 `grep -r "alert"` 找到包含告警相关的路由文件
   - 查阅 `/app/src/routes/dashboard.ts` 确认 Dashboard API 逻辑
   - 查阅 `/app/src/routes/alerts.ts` 确认告警查询逻辑
7. **数据表关联**:
   - `alerts` 表为告警核心数据表
   - 与 `stores` 表、`equipment` 表通过外键关联

## 根因分析
通过代码静态分析确定根本原因：

| 证据来源 | 发现内容 |
|----------|----------|
| `/app/src/db/schema.ts` | 定义了 `alerts` 表结构，包含 level、status、storeId、equipmentId 等字段 |
| `/app/src/routes/alerts.ts` | API 实现直接查询 `alerts` 表，支持按 store_id、level、status 过滤 |
| `/app/src/routes/dashboard.ts` | 仪表盘接口中统计告警数量时查询 `alerts` 表的 open/critical 状态 |
| 数据库连接配置 | PostgreSQL `kfc_monitor` 数据库，表名为 `alerts` |

结论：**告警分布图表的核心数据源为 `alerts` 表**

## 修复措施
本事件为信息咨询类问题，非故障修复场景：

| 操作项 | 验证结果 |
|--------|----------|
| 代码静态分析完成 | ✅ 已确认 `alerts` 表为核心数据源 |
| 数据库 Schema 映射 | ✅ stores/equipment/alerts 三表关系已明确 |
| API 接口文档 | ✅ GET /api/alerts 和 GET /api/dashboard/overview 已确认 |
| SQL 查询示例 | ✅ 提供按级别/状态/区域统计的查询语句供参考 |

### 关键信息汇总
```
数据库类型：PostgreSQL
数据库名：kfc_monitor
连接地址：localhost:5433
用户名：kfc
密码：kfc123 (生产环境应修改)

核心表：alerts
关联表：stores, equipment
```