# 事件排查报告

## 事件概要
- **标题**: KFC项目区域营收图表数据表查询分析
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
用户咨询KFC项目中区域营收图表所查询的数据表信息，涉及业务数据结构梳理和后端代码分析。

## 排查过程
按时间顺序执行以下关键排查步骤：

| 步骤 | 操作命令 | 发现结果 |
|------|----------|----------|
| 1 | `list_servers()` | 定位到KFC生产服务器 `431d0275-ac52-42ac-ae15-91a417c21c60` (localhost) |
| 2 | `find / -name "*.py" -o -name "*.js" -o -name "*.sql"` | 查看系统级代码文件分布 |
| 3 | `ls -la /opt/ /var/www/ /home/` | 确认 `/app/` 目录为应用主目录 |
| 4 | `ps aux \| grep -E "node\|python\|mysql\|nginx"` | 发现Node.js进程正在运行 (`tsx src/index.ts`) |
| 5 | `ls -la /app/src/` | 发现核心目录：`db/`, `routes/`, `index.ts` |
| 6 | `find /app/src -type f -name "*.ts" \| xargs cat` | 读取全部TypeScript源码，找到数据库Schema定义 |
| 7 | `grep -r "region\|营收\|revenue" /app/src --include="*.ts"` | 精确定位区域和营收相关字段定义 |

## 根因分析
**非故障排查，为信息查询类请求**。通过代码静态分析定位数据源：

1. **stores 表** (存储门店信息)
   ```typescript
   export const stores = pgTable("stores", {
     id: serial("id").primaryKey(),
     code: varchar("code", { length: 20 }),      // 门店编码
     name: varchar("name", { length: 100 }),     // 门店名称
     region: varchar("region", { length: 20 }),  // 区域字段
     city: varchar("city", { length: 50 }),      // 城市
     ...
   });
   ```

2. **daily_sales 表** (存储每日销售数据)
   ```typescript
   export const daily_sales = pgTable("daily_sales", {
     store_id: integer("store_id"),              // FK → stores.id
     date: date("date"),                         // 日期
     revenue: numeric("revenue", { precision: 10, scale: 2 }),  // 营收金额
     order_count: integer("order_count"),        // 订单数
     avg_order_value: numeric("avg_order_value", { precision: 8, scale: 2 }),
     created_at: timestamp("created_at"),
     ...
   });
   ```

3. **关联关系**
   - `daily_sales.store_id` → `stores.id` (外键关联)
   - 按 `stores.region` 分组聚合 `revenue` 计算区域总营收

## 修复措施
### 执行操作
无需技术修复，通过代码分析完成信息查询。

### 验证结果
已确认以下API接口支持区域营收统计：

| 接口路径 | 方法 | 功能说明 |
|----------|------|----------|
| `/api/dashboard/region-stats` | GET | 按区域统计门店数、设备数、告警数、今日营收 |
| `/api/sales` | GET | 支持按 `store_id` 和 `date` 查询 |
| `/api/sales/trend` | GET | 获取门店销售趋势（最近7天） |

### 最终结论
✅ **区域营收图表的核心查询逻辑**：
```sql
-- 伪SQL查询示例
SELECT 
    s.region,
    SUM(ds.revenue) as total_revenue,
    COUNT(s.id) as store_count
FROM daily_sales ds
JOIN stores s ON ds.store_id = s.id
GROUP BY s.region;
```

---
*报告生成时间: 当前会话结束*