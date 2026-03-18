# KFC 门店监控系统 — 运维手册

## 1. 项目概述

KFC 门店监控系统是一套面向全国 KFC 门店的运营状态监控平台，旨在为运维团队和 Chronos AI Agent 提供全面的门店运营可观测性。

- **系统用途**：实时监控全国 KFC 门店运营状态，提供故障预警、设备管理、巡检跟踪和销售分析等功能
- **覆盖范围**：15 家门店、60 台设备
- **核心功能**：
  - **实时告警**：设备故障、运营异常等告警的创建、跟踪和处理
  - **设备状态监控**：POS 机、冷柜、油炸锅、空调等设备的运行状态实时监控
  - **巡检管理**：门店巡检计划制定、巡检记录管理、评分统计
  - **销售分析**：每日营收、订单量、客单价等销售数据的统计与趋势分析

## 2. 技术架构

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Web 前端     │────▶│   后端 API     │────▶│  PostgreSQL   │
│  React+Nginx  │     │  Node.js+Hono │     │   17-alpine   │
│   port 3000   │     │   port 3001   │     │   port 5432   │
└───────────────┘     └───────────────┘     └───────────────┘
```

| 层级 | 技术栈 | 容器端口 | 宿主机端口 |
|------|--------|----------|------------|
| 前端 | React + TanStack Router + TanStack Query + Tailwind CSS + Nginx | 80 | 3000 |
| 后端 | Node.js + Hono + Drizzle ORM + Pino | 3001 | 3001 |
| 数据库 | PostgreSQL 17 (Alpine) | 5432 | 5433 |
| SSH | Backend 容器内置 SSH | 100 | 2222 |

### 容器间通信

- Web 容器通过 Nginx 反向代理将 `/api/` 请求转发到 `http://backend:3001/api/`
- 后端容器通过 Docker 内部网络连接 PostgreSQL：`postgres://kfc:kfc123@postgres:5432/kfc_monitor`

## 3. 服务连接信息

### PostgreSQL 数据库

```bash
# 从容器内部连接
psql -h postgres -U kfc -d kfc_monitor
# 密码: 123456

# 从宿主机连接
psql -h localhost -p 5433 -U kfc -d kfc_monitor
# 密码: 123456
```

### API 接口

```bash
# 容器内部访问
curl http://backend:3001/api/stores

# 宿主机访问
curl http://localhost:3001/api/stores

# 通过 Web 前端代理访问
curl http://localhost:3000/api/stores
```

### SSH 远程管理

```bash
# 从宿主机 SSH 到后端容器
ssh root@localhost -p 2222
# 密码: 123456
```

## 4. 数据库 Schema

系统共包含 5 张数据表，以下是各表的详细结构。

### 4.1 stores（门店表）

| 列名 | 类型 | 约束 | 描述 |
|------|------|------|------|
| id | serial | PRIMARY KEY | 门店唯一标识 |
| code | varchar(20) | UNIQUE, NOT NULL | 门店编码，如 `KFC-GZ-001` |
| name | varchar(100) | NOT NULL | 门店名称 |
| address | text | NOT NULL | 门店地址 |
| city | varchar(50) | NOT NULL | 所在城市 |
| region | varchar(20) | NOT NULL | 所在区域（华南、华东等） |
| status | varchar(20) | NOT NULL, DEFAULT 'normal' | 门店状态：normal / warning / error |
| manager | varchar(50) | NOT NULL | 店长姓名 |
| phone | varchar(20) | NOT NULL | 联系电话 |
| created_at | timestamp | NOT NULL, DEFAULT now() | 创建时间 |
| updated_at | timestamp | NOT NULL, DEFAULT now() | 更新时间 |

**关联关系**：一对多关联 equipment、alerts、inspection_records、daily_sales

### 4.2 equipment（设备表）

| 列名 | 类型 | 约束 | 描述 |
|------|------|------|------|
| id | serial | PRIMARY KEY | 设备唯一标识 |
| store_id | integer | NOT NULL, FK → stores.id | 所属门店 ID |
| name | varchar(100) | NOT NULL | 设备名称 |
| type | varchar(30) | NOT NULL | 设备类型：pos / freezer / fryer / ac 等 |
| model | varchar(100) | NOT NULL | 设备型号 |
| status | varchar(20) | NOT NULL, DEFAULT 'normal' | 设备状态：normal / warning / error / offline |
| installed_at | timestamp | | 安装时间 |
| last_maintenance_at | timestamp | | 最近维护时间 |
| created_at | timestamp | NOT NULL, DEFAULT now() | 创建时间 |
| updated_at | timestamp | NOT NULL, DEFAULT now() | 更新时间 |

**关联关系**：多对一关联 stores，一对多关联 alerts

### 4.3 alerts（告警表）

| 列名 | 类型 | 约束 | 描述 |
|------|------|------|------|
| id | serial | PRIMARY KEY | 告警唯一标识 |
| store_id | integer | NOT NULL, FK → stores.id | 所属门店 ID |
| equipment_id | integer | FK → equipment.id | 关联设备 ID（可为空，非设备告警时） |
| level | varchar(20) | NOT NULL | 告警级别：info / warning / critical |
| title | varchar(200) | NOT NULL | 告警标题 |
| description | text | NOT NULL | 告警详细描述 |
| status | varchar(20) | NOT NULL, DEFAULT 'open' | 告警状态：open / acknowledged / resolved |
| created_at | timestamp | NOT NULL, DEFAULT now() | 告警创建时间 |
| resolved_at | timestamp | | 解决时间 |
| resolved_by | varchar(50) | | 解决人 |

**关联关系**：多对一关联 stores，多对一关联 equipment

### 4.4 inspection_records（巡检记录表）

| 列名 | 类型 | 约束 | 描述 |
|------|------|------|------|
| id | serial | PRIMARY KEY | 巡检记录唯一标识 |
| store_id | integer | NOT NULL, FK → stores.id | 所属门店 ID |
| inspector_name | varchar(50) | NOT NULL | 巡检员姓名 |
| score | integer | NOT NULL | 巡检评分（满分 100） |
| items | jsonb | NOT NULL | 巡检项明细（JSON 格式，包含各项检查结果） |
| remarks | text | | 备注信息 |
| inspected_at | timestamp | NOT NULL | 巡检时间 |

**关联关系**：多对一关联 stores

**items JSONB 结构示例**：
```json
[
  { "name": "食品安全", "score": 25, "maxScore": 25, "passed": true },
  { "name": "环境卫生", "score": 20, "maxScore": 25, "passed": false, "remark": "厨房地面有油渍" },
  { "name": "设备运行", "score": 23, "maxScore": 25, "passed": true },
  { "name": "服务规范", "score": 22, "maxScore": 25, "passed": true }
]
```

### 4.5 daily_sales（每日销售表）

| 列名 | 类型 | 约束 | 描述 |
|------|------|------|------|
| id | serial | PRIMARY KEY | 记录唯一标识 |
| store_id | integer | NOT NULL, FK → stores.id | 所属门店 ID |
| date | date | NOT NULL | 销售日期 |
| revenue | numeric(10,2) | NOT NULL | 当日营收（元） |
| order_count | integer | NOT NULL | 订单数量 |
| avg_order_value | numeric(8,2) | NOT NULL | 客单价（元） |
| created_at | timestamp | NOT NULL, DEFAULT now() | 记录创建时间 |

**关联关系**：多对一关联 stores

## 5. API 端点

所有 API 均以 `/api` 为前缀。

### 5.1 门店管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/stores | 获取全部门店列表 |
| GET | /api/stores/:id | 获取指定门店详情（含关联设备和告警） |
| POST | /api/stores | 创建新门店 |
| PUT | /api/stores/:id | 更新门店信息 |
| DELETE | /api/stores/:id | 删除门店 |

### 5.2 设备管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/equipment | 获取全部设备列表 |
| GET | /api/equipment/:id | 获取指定设备详情 |
| GET | /api/stores/:id/equipment | 获取指定门店的所有设备 |
| POST | /api/equipment | 创建新设备 |
| PUT | /api/equipment/:id | 更新设备信息（含状态变更） |
| DELETE | /api/equipment/:id | 删除设备 |

### 5.3 告警管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/alerts | 获取全部告警列表（支持 status/level 过滤） |
| GET | /api/alerts/:id | 获取指定告警详情 |
| GET | /api/stores/:id/alerts | 获取指定门店的所有告警 |
| POST | /api/alerts | 创建新告警 |
| PUT | /api/alerts/:id | 更新告警信息 |
| PUT | /api/alerts/:id/resolve | 解决告警（设置 resolved_at 和 resolved_by） |

### 5.4 巡检管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/inspections | 获取全部巡检记录 |
| GET | /api/inspections/:id | 获取指定巡检记录详情 |
| GET | /api/stores/:id/inspections | 获取指定门店的巡检记录 |
| POST | /api/inspections | 创建新巡检记录 |

### 5.5 销售数据

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/sales | 获取全部销售数据（支持日期范围过滤） |
| GET | /api/stores/:id/sales | 获取指定门店的销售数据 |
| POST | /api/sales | 录入每日销售数据 |

### 5.6 统计概览

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/dashboard/summary | 获取系统概览统计（门店总数、告警数、设备状态分布等） |
| GET | /api/dashboard/alerts-trend | 获取告警趋势数据 |
| GET | /api/dashboard/sales-overview | 获取销售总览数据 |

## 6. 常见排查路径

### 6.1 门店告警排查

**场景**：某门店触发告警，需要快速了解告警详情、关联设备和门店信息。

**排查步骤**：

1. 查看当前未解决的告警，按门店分组统计：

```sql
SELECT s.name AS store_name, s.code AS store_code,
       COUNT(*) AS alert_count,
       COUNT(*) FILTER (WHERE a.level = 'critical') AS critical_count
FROM alerts a
JOIN stores s ON a.store_id = s.id
WHERE a.status = 'open'
GROUP BY s.id, s.name, s.code
ORDER BY critical_count DESC, alert_count DESC;
```

2. 查看特定门店的告警详情（关联设备信息）：

```sql
SELECT a.id, a.level, a.title, a.description, a.created_at,
       e.name AS equipment_name, e.type AS equipment_type, e.status AS equipment_status
FROM alerts a
LEFT JOIN equipment e ON a.equipment_id = e.id
WHERE a.store_id = (SELECT id FROM stores WHERE code = 'KFC-GZ-001')
  AND a.status = 'open'
ORDER BY
  CASE a.level WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
  a.created_at DESC;
```

3. 检查该门店的整体运营状态：

```sql
SELECT s.*,
       (SELECT COUNT(*) FROM equipment e WHERE e.store_id = s.id AND e.status != 'normal') AS abnormal_equipment_count,
       (SELECT COUNT(*) FROM alerts a WHERE a.store_id = s.id AND a.status = 'open') AS open_alerts_count
FROM stores s
WHERE s.code = 'KFC-GZ-001';
```

### 6.2 设备故障诊断

**场景**：需要排查设备故障，找出异常设备并关联历史告警。

**排查步骤**：

1. 查询所有异常设备及其所属门店：

```sql
SELECT e.id, e.name, e.type, e.model, e.status,
       e.installed_at, e.last_maintenance_at,
       s.name AS store_name, s.code AS store_code, s.city
FROM equipment e
JOIN stores s ON e.store_id = s.id
WHERE e.status != 'normal'
ORDER BY
  CASE e.status WHEN 'error' THEN 1 WHEN 'offline' THEN 2 WHEN 'warning' THEN 3 END,
  e.updated_at DESC;
```

2. 查看特定设备的历史告警记录：

```sql
SELECT a.id, a.level, a.title, a.description, a.status,
       a.created_at, a.resolved_at, a.resolved_by
FROM alerts a
WHERE a.equipment_id = 5  -- 替换为目标设备 ID
ORDER BY a.created_at DESC
LIMIT 20;
```

3. 检查需要维护的设备（超过 90 天未维护）：

```sql
SELECT e.name, e.type, e.model, e.last_maintenance_at,
       s.name AS store_name,
       EXTRACT(DAY FROM now() - e.last_maintenance_at) AS days_since_maintenance
FROM equipment e
JOIN stores s ON e.store_id = s.id
WHERE e.last_maintenance_at < now() - INTERVAL '90 days'
ORDER BY e.last_maintenance_at ASC;
```

### 6.3 销售异常分析

**场景**：某门店销售数据异常，需要对比历史数据并关联 POS 设备状态。

**排查步骤**：

1. 对比近 7 天与上周同期销售数据：

```sql
WITH recent AS (
  SELECT store_id, date, revenue, order_count, avg_order_value
  FROM daily_sales
  WHERE date >= CURRENT_DATE - INTERVAL '7 days'
),
previous AS (
  SELECT store_id, date + 7 AS comparable_date, revenue, order_count, avg_order_value
  FROM daily_sales
  WHERE date >= CURRENT_DATE - INTERVAL '14 days'
    AND date < CURRENT_DATE - INTERVAL '7 days'
)
SELECT s.name AS store_name, s.code,
       r.date,
       r.revenue AS current_revenue,
       p.revenue AS previous_revenue,
       ROUND(((r.revenue - p.revenue) / p.revenue * 100)::numeric, 1) AS revenue_change_pct
FROM recent r
JOIN previous p ON r.store_id = p.store_id AND r.date = p.comparable_date
JOIN stores s ON r.store_id = s.id
WHERE ABS((r.revenue - p.revenue) / p.revenue) > 0.2  -- 波动超过 20%
ORDER BY ABS((r.revenue - p.revenue) / p.revenue) DESC;
```

2. 检查销售异常门店的 POS 设备状态：

```sql
SELECT e.name, e.type, e.model, e.status, e.last_maintenance_at,
       s.name AS store_name
FROM equipment e
JOIN stores s ON e.store_id = s.id
WHERE e.type = 'pos'
  AND s.code = 'KFC-GZ-001'  -- 替换为目标门店编码
ORDER BY e.status DESC;
```

3. 查看门店历史销售趋势（近 30 天）：

```sql
SELECT ds.date, ds.revenue, ds.order_count, ds.avg_order_value,
       AVG(ds.revenue) OVER (ORDER BY ds.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS revenue_7d_avg
FROM daily_sales ds
WHERE ds.store_id = (SELECT id FROM stores WHERE code = 'KFC-GZ-001')
  AND ds.date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY ds.date DESC;
```

### 6.4 巡检评分下降

**场景**：某门店巡检评分出现下降趋势，需要分析具体原因。

**排查步骤**：

1. 查看门店巡检评分趋势：

```sql
SELECT ir.inspected_at, ir.inspector_name, ir.score, ir.remarks
FROM inspection_records ir
WHERE ir.store_id = (SELECT id FROM stores WHERE code = 'KFC-SH-001')
ORDER BY ir.inspected_at DESC
LIMIT 10;
```

2. 分析巡检项目明细（展开 JSONB）：

```sql
SELECT ir.inspected_at, ir.score,
       item->>'name' AS item_name,
       (item->>'score')::int AS item_score,
       (item->>'maxScore')::int AS max_score,
       (item->>'passed')::boolean AS passed,
       item->>'remark' AS item_remark
FROM inspection_records ir,
     jsonb_array_elements(ir.items) AS item
WHERE ir.store_id = (SELECT id FROM stores WHERE code = 'KFC-SH-001')
  AND ir.inspected_at >= now() - INTERVAL '90 days'
ORDER BY ir.inspected_at DESC, item_name;
```

3. 统计各巡检项目的平均得分率（找出薄弱环节）：

```sql
SELECT item->>'name' AS item_name,
       ROUND(AVG((item->>'score')::numeric / (item->>'maxScore')::numeric * 100), 1) AS avg_score_pct,
       COUNT(*) FILTER (WHERE (item->>'passed')::boolean = false) AS fail_count,
       COUNT(*) AS total_count
FROM inspection_records ir,
     jsonb_array_elements(ir.items) AS item
WHERE ir.store_id = (SELECT id FROM stores WHERE code = 'KFC-SH-001')
  AND ir.inspected_at >= now() - INTERVAL '90 days'
GROUP BY item->>'name'
ORDER BY avg_score_pct ASC;
```

4. 跨门店对比巡检评分（发现区域性问题）：

```sql
SELECT s.name AS store_name, s.code, s.city, s.region,
       ROUND(AVG(ir.score), 1) AS avg_score,
       MIN(ir.score) AS min_score,
       MAX(ir.score) AS max_score,
       COUNT(*) AS inspection_count
FROM inspection_records ir
JOIN stores s ON ir.store_id = s.id
WHERE ir.inspected_at >= now() - INTERVAL '90 days'
GROUP BY s.id, s.name, s.code, s.city, s.region
ORDER BY avg_score ASC;
```

## 7. 常用 SQL 查询示例

### 查看所有未解决的告警

```sql
SELECT a.*, s.name AS store_name
FROM alerts a
JOIN stores s ON a.store_id = s.id
WHERE a.status = 'open'
ORDER BY a.created_at DESC;
```

### 查看设备异常

```sql
SELECT e.*, s.name AS store_name
FROM equipment e
JOIN stores s ON e.store_id = s.id
WHERE e.status != 'normal';
```

### 门店销售趋势

```sql
SELECT ds.*, s.name
FROM daily_sales ds
JOIN stores s ON ds.store_id = s.id
WHERE s.code = 'KFC-GZ-001'
ORDER BY ds.date DESC;
```

### 查看特定门店巡检记录

```sql
SELECT ir.*, s.name
FROM inspection_records ir
JOIN stores s ON ir.store_id = s.id
WHERE s.code = 'KFC-SH-001'
ORDER BY ir.inspected_at DESC;
```

### 系统概览统计

```sql
SELECT
  (SELECT COUNT(*) FROM stores) AS total_stores,
  (SELECT COUNT(*) FROM stores WHERE status != 'normal') AS abnormal_stores,
  (SELECT COUNT(*) FROM equipment) AS total_equipment,
  (SELECT COUNT(*) FROM equipment WHERE status != 'normal') AS abnormal_equipment,
  (SELECT COUNT(*) FROM alerts WHERE status = 'open') AS open_alerts,
  (SELECT COUNT(*) FROM alerts WHERE status = 'open' AND level = 'critical') AS critical_alerts;
```

### 各城市门店运营概况

```sql
SELECT s.city,
       COUNT(DISTINCT s.id) AS store_count,
       COUNT(DISTINCT e.id) AS equipment_count,
       COUNT(DISTINCT a.id) FILTER (WHERE a.status = 'open') AS open_alerts,
       ROUND(AVG(ir.score), 1) AS avg_inspection_score
FROM stores s
LEFT JOIN equipment e ON e.store_id = s.id
LEFT JOIN alerts a ON a.store_id = s.id
LEFT JOIN inspection_records ir ON ir.store_id = s.id
  AND ir.inspected_at >= now() - INTERVAL '30 days'
GROUP BY s.city
ORDER BY store_count DESC;
```

### 今日/昨日销售对比

```sql
SELECT s.name AS store_name, s.code,
       today.revenue AS today_revenue,
       yesterday.revenue AS yesterday_revenue,
       ROUND(((today.revenue - yesterday.revenue) / yesterday.revenue * 100)::numeric, 1) AS change_pct
FROM stores s
LEFT JOIN daily_sales today ON today.store_id = s.id AND today.date = CURRENT_DATE
LEFT JOIN daily_sales yesterday ON yesterday.store_id = s.id AND yesterday.date = CURRENT_DATE - 1
WHERE today.revenue IS NOT NULL
ORDER BY change_pct DESC NULLS LAST;
```
