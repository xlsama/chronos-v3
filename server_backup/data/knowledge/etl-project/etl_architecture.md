# ETL 数据管道架构文档

## 概述

本项目运行一个三层 ETL 数据管道，用于将交易订单数据从源数据库经过清洗转换加载到分析报表数据库。

## 数据库架构

### 1. 上游源数据库 (mysql-etl-source)

- **类型**: MySQL 8.0
- **主机**: localhost
- **端口**: 13307
- **数据库名**: source_db
- **用户名**: etl_user
- **密码**: sourcepass
- **说明**: 存储原始交易订单数据，包含 orders 表和 products 表

**orders 表结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| order_no | VARCHAR(32) | 订单编号 (ORD-000001 格式) |
| customer_id | INT | 客户ID |
| product_id | INT | 产品ID (关联 products 表) |
| quantity | INT | 数量 |
| unit_price | DECIMAL(10,2) | 单价 |
| total_amount | DECIMAL(10,2) | 总金额 (quantity × unit_price) |
| order_date | DATE | 订单日期 |
| status | VARCHAR(20) | 订单状态: completed / cancelled |
| region | VARCHAR(20) | 区域: north / south / east / west |

**products 表结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| name | VARCHAR(100) | 产品名称 |
| category | VARCHAR(50) | 产品类别: electronics / accessories / tools |
| price | DECIMAL(10,2) | 标准价格 |

### 2. 中间清洗数据库 (mysql-etl-staging)

- **类型**: MySQL 8.0
- **主机**: localhost
- **端口**: 13308
- **数据库名**: staging_db
- **用户名**: etl_user
- **密码**: stagingpass
- **说明**: 存储清洗和转换后的订单数据，只应包含 completed 状态的订单

**clean_orders 表结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| source_order_id | INT | 对应源表的 order ID |
| order_no | VARCHAR(32) | 订单编号 |
| customer_id | INT | 客户ID |
| product_id | INT | 产品ID |
| product_name | VARCHAR(100) | 产品名称 (从 products 表 JOIN 获取) |
| category | VARCHAR(50) | 产品类别 (从 products 表 JOIN 获取) |
| quantity | INT | 数量 |
| unit_price | DECIMAL(10,2) | 单价 |
| total_amount | DECIMAL(10,2) | 总金额 |
| order_date | DATE | 订单日期 |
| region | VARCHAR(20) | 区域 |

### 3. 下游目标数据库 (mysql-etl-target)

- **类型**: MySQL 8.0
- **主机**: localhost
- **端口**: 13309
- **数据库名**: target_db
- **用户名**: etl_user
- **密码**: targetpass
- **说明**: 存储聚合后的分析报表数据

**daily_sales_summary 表结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| order_date | DATE | 日期 |
| region | VARCHAR(20) | 区域 |
| category | VARCHAR(50) | 产品类别 |
| order_count | INT | 订单数 |
| total_quantity | INT | 总数量 |
| total_revenue | DECIMAL(12,2) | 总收入 |

## ETL 流程

### Pipeline 1: 源库 → 清洗库

1. 从 source_db.orders 提取 `status = 'completed'` 的订单（过滤掉 cancelled）
2. JOIN products 表获取产品名称和类别
3. 写入 staging_db.clean_orders

关键 SQL:
```sql
SELECT o.*, p.name AS product_name, p.category
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.status = 'completed'
```

### Pipeline 2: 清洗库 → 目标库

1. 从 staging_db.clean_orders 按 (order_date, region, category) 分组聚合
2. 计算 order_count, total_quantity, total_revenue
3. 写入 target_db.daily_sales_summary

关键 SQL:
```sql
SELECT order_date, region, category,
       COUNT(*) AS order_count,
       SUM(quantity) AS total_quantity,
       SUM(total_amount) AS total_revenue
FROM clean_orders
GROUP BY order_date, region, category
```

## 排查原则

遇到“下游汇总结果与上游明细不一致”时，不要直接把问题归因到当前看到差异的那一层，而应先识别这条链路的分层职责，再按 `source -> staging -> target` 的顺序逐层验证，定位**第一处**出现差异的环节。

推荐顺序：

1. 先确认 source_db 中业务基线是否正常
2. 再确认 source_db → staging_db 是否一致
3. 最后确认 staging_db → target_db 是否一致
4. 若下游异常但上游已先出现差异，应优先将上游差异视为根因候选，下游异常可能只是连带结果

没有脚本、日志或配置证据时，可以提出假设，但必须与已验证事实明确区分，不能把推测直接写成结论。

## 数据校验规则

### 规则 1: 源库 → 清洗库一致性
staging_db.clean_orders 的总行数 **必须等于** source_db.orders 中 `status = 'completed'` 的行数。

验证 SQL:
```sql
-- 在 source_db 上执行
SELECT COUNT(*) AS source_completed FROM orders WHERE status = 'completed';

-- 在 staging_db 上执行
SELECT COUNT(*) AS staging_total FROM clean_orders;

-- 两个结果应该相等
```

### 规则 2: 清洗库 → 目标库一致性
target_db.daily_sales_summary 的 `SUM(order_count)` **必须等于** staging_db.clean_orders 的总行数。

验证 SQL:
```sql
-- 在 target_db 上执行
SELECT SUM(order_count) AS target_total_orders FROM daily_sales_summary;

-- 在 staging_db 上执行
SELECT COUNT(*) AS staging_total FROM clean_orders;

-- 两个结果应该相等
```

### 规则 3: 端到端一致性
target_db 的总订单数 = source_db 中 completed 订单数。

## 常见问题排查

### 问题 1: 清洗库行数 > 源库 completed 行数
**原因**: ETL 脚本从源库提取数据时，WHERE 条件缺失或不正确，导致 cancelled 订单也被提取到清洗库。
**排查方法**: 
- 检查 staging_db.clean_orders 中是否存在对应 source_db 中 status='cancelled' 的订单
- 对比 source_order_id，查找不应存在的记录

### 问题 2: 目标库聚合总数 ≠ 清洗库行数
**原因**: 
- 清洗库数据更新后，聚合 ETL 未重新运行，导致目标库数据过时
- 或者聚合 SQL 逻辑有误
**排查方法**:
- 比较 staging_db 的 etl_loaded_at 和 target_db 的 etl_loaded_at 时间戳
- 如果清洗库更新时间晚于目标库，说明聚合未重跑

### 问题 3: 端到端数据差异
**排查步骤**:
1. 先确认源库 completed 订单数
2. 再确认清洗库总行数（是否一致？如不一致，参见问题 1）
3. 最后确认目标库聚合总数（是否与清洗库一致？如不一致，参见问题 2）
4. 逐层定位差异出现在哪个环节
