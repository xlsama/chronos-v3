# 事件排查报告

## 事件概要
- 标题: 区域营收数据源表结构确认
- 严重程度: P3
- 处理状态: 已解决

## 问题描述
- **受影响服务**: KFC 生产服务器业务应用（基于 Node.js/Hono 框架）
- **症状**: 业务侧需明确区域营收统计功能所关联的底层数据库表及逻辑。
- **影响范围**: 数据统计与报表开发链路，涉及营收查询接口的数据溯源。

## 排查过程
1. **环境确认**: 
   - 调用 `list_servers()` 工具确认目标服务器为 "KFC 生产服务器" (localhost)，状态 online。
2. **目录结构探查**: 
   - 执行 `ls -la /app/` 等命令，定位项目根目录在 `/app/`，发现包含 `src`, `node_modules`, `Dockerfile` 等标准工程结构。
3. **代码文件定位**: 
   - 使用 `find` 命令检索 `/app/src` 下的源码文件，锁定关键路由文件：`/app/src/routes/sales.ts`、`/app/src/routes/dashboard.ts` 及数据库定义文件 `/app/src/db/schema.ts`。
4. **数据库模型分析**: 
   - 读取 `schema.ts`，确认存在 `stores`（门店）、`equipment`（设备）、`dailySales`（每日销售）等表定义。其中 `stores` 表包含 `region` 字段用于标识区域。
5. **查询逻辑验证**: 
   - 查阅 `sales.ts` 和 `dashboard.ts` 接口代码，确认营收数据存储在 `dailySales` 表中，并通过 `dailySales.storeId` 外键关联 `stores.id`，按 `stores.region` 进行分组聚合计算。

## 根因分析
- **数据源头**: 营收数据来源于 `daily_sales` 表（代码中定义为 `dailySales`），该表包含 `revenue`（营收）、`orderCount`（订单数）等关键字段。
- **区域关联**: 区域维度通过 `stores` 表的 `region` 字段提供。
- **实现方式**: 后端 API 使用 Drizzle ORM 框架，通过 JOIN 操作将 `daily_sales` 与 `stores` 表关联，并在 `dashboard.ts` 或 `sales.ts` 中进行聚合统计（如 `sum(dailySales.revenue)`）。
- **结论**: 区域营收查询的核心依赖表为 `daily_sales` 表，并结合 `stores` 表完成区域维度的过滤与分组。

## 修复措施
- **信息输出**: 向用户提供了完整的表结构分析及查询链路说明，明确了以下映射关系：
  - 核心数据表：`daily_sales`
  - 关联维度表：`stores`
  - 关键字段：`daily_sales.revenue`, `stores.region`
- **验证结果**: 用户已获取所需数据表信息，问题闭环。