# Chronos Agent 演示问答

> 演示 AI Agent 通过 SSH 连接到 KFC 监控系统后端容器，执行运维查询和排障的能力。
>
> 数据库连接：`psql -h postgres -U kfc -d kfc_monitor`

---

## Q1: 数据库探查

### 提问

> 这个系统有哪些表？各有多少数据？

### Agent 思考过程

```
思考：用户想了解数据库的整体结构。我需要先连接数据库，查看有哪些表，然后统计各表的数据量。

步骤 1 — SSH 连接到后端容器
工具调用：ssh kfc-backend

步骤 2 — 查看所有用户表
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "\dt"

结果：找到 5 张表 — stores, equipment, alerts, inspection_records, daily_sales

步骤 3 — 统计各表行数
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT 'stores' AS table_name, COUNT(*) FROM stores
    UNION ALL SELECT 'equipment', COUNT(*) FROM equipment
    UNION ALL SELECT 'alerts', COUNT(*) FROM alerts
    UNION ALL SELECT 'inspection_records', COUNT(*) FROM inspection_records
    UNION ALL SELECT 'daily_sales', COUNT(*) FROM daily_sales;
  "

结果：获得各表行数统计
```

### 预期回答

这个系统的数据库（kfc_monitor）共有 **5 张业务表**：

| 表名 | 说明 | 数据量 |
|------|------|--------|
| `stores` | 门店信息 | 15 条 |
| `equipment` | 设备信息 | 60 条 |
| `alerts` | 告警记录 | 30 条 |
| `inspection_records` | 巡检记录 | 20 条 |
| `daily_sales` | 每日销售 | 45 条 |

整体来看，这是一个 KFC 门店运维监控系统，覆盖了 15 家门店，管理着 60 台设备，并记录了告警、巡检和销售数据。

---

## Q2: 严重告警排查

### 提问

> 目前有哪些未解决的严重告警？

### Agent 思考过程

```
思考：用户想了解当前未处理的严重告警。我需要查询 alerts 表中 status='open' 且 level='critical' 的记录，
并关联门店和设备信息来给出完整的影响分析。

步骤 1 — SSH 连接到后端容器
工具调用：ssh kfc-backend

步骤 2 — 查询未解决的严重告警，关联门店和设备
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT a.id, s.code, s.name AS store_name, e.name AS equipment_name,
           a.level, a.title, a.description, a.created_at
    FROM alerts a
    JOIN stores s ON a.store_id = s.id
    LEFT JOIN equipment e ON a.equipment_id = e.id
    WHERE a.status = 'open' AND a.level = 'critical'
    ORDER BY a.created_at DESC;
  "

结果：找到 5 条 critical open 告警

步骤 3 — 补充查询 warning 级别的 open 告警
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT a.id, s.code, s.name AS store_name, e.name AS equipment_name,
           a.level, a.title, a.description, a.created_at
    FROM alerts a
    JOIN stores s ON a.store_id = s.id
    LEFT JOIN equipment e ON a.equipment_id = e.id
    WHERE a.status = 'open' AND a.level = 'warning'
    ORDER BY a.created_at DESC;
  "

结果：找到 2 条 warning open 告警

步骤 4 — 汇总分析，按门店分组评估影响
```

### 预期回答

当前共有 **7 条未解决告警**（5 条 critical + 2 条 warning），涉及 3 家门店：

#### 🔴 KFC-SH-001 上海南京路店 — 3 条 critical

| 告警 | 设备 | 描述 | 时间 |
|------|------|------|------|
| 设备温度过高 | 油炸锅 | 温度已达 210°C，超过安全阈值 200°C | 昨天 |
| 油炸锅压力异常 | 油炸锅 | 压力值异常偏高，超出正常工作范围 | 昨天 |
| 空调制冷异常 | 商用烤箱 | 厨房室温已达 35°C，空调制冷系统可能故障 | 2 天前 |

**影响评估**：该门店油炸锅存在温度和压力双重异常，存在安全隐患，建议立即停机检修。同时厨房温度过高会影响食品安全和员工工作环境。

#### 🔴 KFC-BJ-002 北京中关村店 — 1 条 critical + 1 条 warning

| 告警 | 设备 | 描述 | 时间 |
|------|------|------|------|
| 冷冻柜温度超标 -2°C | 商用冷冻柜 | 温度升至 -2°C，远高于标准 -18°C | 昨天 |
| 冷冻柜除霜周期异常 | 商用冷冻柜 | 除霜周期异常，制冷效率下降 | 2 天前 |

**影响评估**：冷冻柜温度严重超标，食材安全存在重大风险。除霜周期异常可能是温度超标的根因，两个问题可能关联。建议立即转移食材并安排维修。

#### 🔴 KFC-GZ-001 广州天河城店 — 1 条 critical + 1 条 warning

| 告警 | 设备 | 描述 | 时间 |
|------|------|------|------|
| POS 系统无响应 | POS 收银终端 | 无法完成点单和结算，严重影响营业 | 昨天 |
| POS 打印机故障 | POS 收银终端 | 打印机无法正常出票 | 2 天前 |

**影响评估**：POS 系统完全瘫痪，直接导致门店无法正常收银，对营业额影响极大。这与该店昨日销售额骤降直接相关。

**建议优先级**：SH-001（安全隐患） > BJ-002（食材安全） > GZ-001（营业影响）

---

## Q3: 销售异常分析

### 提问

> 广州天河城店昨天销售为什么这么低？

### Agent 思考过程

```
思考：用户提到广州天河城店销售异常低。我需要先查该门店的销售数据确认情况，
然后关联查询告警和设备状态来分析原因。

步骤 1 — SSH 连接到后端容器
工具调用：ssh kfc-backend

步骤 2 — 找到广州天河城店的 store_id
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT id, code, name, status FROM stores WHERE code = 'KFC-GZ-001';
  "

结果：id=5, code=KFC-GZ-001, name=肯德基广州天河城店, status=warning

步骤 3 — 查询该门店近 3 天的销售数据
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT date, revenue, order_count, avg_order_value
    FROM daily_sales
    WHERE store_id = 5
    ORDER BY date DESC;
  "

结果：
  - 今天：正常（¥15,000-35,000 区间）
  - 昨天：revenue=3200.00, order_count=45, avg=71.11  ← 严重异常！
  - 前天：正常（¥15,000-35,000 区间）

步骤 4 — 查询该门店的告警记录
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT a.title, a.level, a.status, a.description, a.created_at,
           e.name AS equipment_name
    FROM alerts a
    LEFT JOIN equipment e ON a.equipment_id = e.id
    WHERE a.store_id = 5 AND a.status = 'open'
    ORDER BY a.created_at DESC;
  "

结果：2 条 open 告警 — POS系统无响应 (critical, 昨天), POS打印机故障 (warning, 2天前)

步骤 5 — 查看设备状态确认
工具调用：执行命令
  psql -h postgres -U kfc -d kfc_monitor -c "
    SELECT name, type, status FROM equipment WHERE store_id = 5;
  "

结果：POS收银终端 status=error，其他设备正常

步骤 6 — 综合分析，建立因果链
```

### 预期回答

广州天河城店（KFC-GZ-001）昨日销售确实严重异常：

**销售数据对比**：

| 日期 | 营业额 | 订单数 | 客单价 |
|------|--------|--------|--------|
| 前天 | ¥15,000~35,000（正常） | 300~700 | ¥45~65 |
| **昨天** | **¥3,200** | **45** | **¥71.11** |
| 今天 | ¥15,000~35,000（正常） | 300~700 | ¥45~65 |

昨日营业额仅 ¥3,200，不到正常水平的 1/5，订单数也从正常的 300~700 单骤降到 45 单。

**根因分析**：

查到该门店有 2 条未解决告警：
1. **POS 打印机故障**（warning，2 天前触发）— 打印头损坏或卡纸，出票异常
2. **POS 系统无响应**（critical，昨天触发）— POS 终端完全无法点单和结算

**因果链**：打印机故障（2 天前）→ POS 系统最终崩溃无响应（昨天）→ 无法正常收银 → 营业额暴跌至 ¥3,200（仅靠手工记账等方式完成少量订单）

**建议**：
1. 立即修复/更换 POS 终端，恢复收银能力
2. 联系设备供应商（Sunmi T2）安排紧急维修
3. 通知门店经理陈明（020-85671234）跟进处理进度

---

## Q4: AI Agent 自动修复

### 场景说明

后端代码 `src/routes/alerts.ts` 的 resolve 接口中预埋了一个 bug：在"同步设备状态"的 raw SQL 查询里，使用了错误的列名 `alert_status`，而 alerts 表的实际列名是 `status`。这个 bug 只有在点击"处理"按钮时才会触发——浏览告警列表、查看详情都不会报错。

### 演示步骤（给演示者看的）

1. **先展示系统一切正常** — 浏览门店列表、设备页面、告警页面，让观众看到系统运行正常
2. **进入告警页面** — 找到一条状态为 `open` 的告警（如 "设备温度过高"）
3. **点击"处理"按钮** — 弹出确认对话框，点击确认
4. **看到报错弹窗** — 页面弹出错误提示，错误信息包含：`column "alert_status" does not exist`
5. **把报错信息发给 Chronos Agent** — 复制错误信息，发送给 Agent 让它自动排查修复
6. **观看 Agent 自动排查修复** — Agent 会自动 SSH 进容器、查日志、搜代码、修复、重启
7. **再次点击"处理"** — 验证修复成功，告警状态变为 `resolved`

### 提问

> 处理告警报错了，帮我看看
>
> ```
> column "alert_status" does not exist
> ```

### Agent 思考过程

```
思考：用户在处理告警时遇到了数据库错误。错误信息显示 "alert_status" 列不存在，
说明后端代码中使用了错误的列名。我需要 SSH 进容器排查源码并修复这个问题。

步骤 1 — SSH 连接到后端容器
工具调用：ssh kfc-backend

步骤 2 — 查看后端日志，确认报错详情
工具调用：执行命令
  cat /root/.pm2/logs/kfc-backend-error.log | tail -30
  # 或查看控制台输出

结果：
  error: column "alert_status" does not exist
  at /app/src/routes/alerts.ts
  code: '42703'

步骤 3 — 搜索代码中使用 alert_status 的位置
工具调用：执行命令
  grep -rn "alert_status" /app/src/

结果：
  /app/src/routes/alerts.ts:126:          AND alert_status = 'open'`

步骤 4 — 查看上下文，确认正确的列名
工具调用：执行命令
  sed -n '120,135p' /app/src/routes/alerts.ts

结果：
  121  // 同步设备状态：如果该设备所有告警都已解决，恢复设备为 normal
  122  if (existing[0].equipmentId) {
  123    const remaining = await db.execute(
  124      sql`SELECT COUNT(*)::int AS count FROM alerts
  125          WHERE equipment_id = ${existing[0].equipmentId}
  126          AND alert_status = 'open'`    ← 错误的列名
  127    );
  ...

步骤 5 — 查看数据库 schema 确认正确列名
工具调用：执行命令
  grep -n "status" /app/src/db/schema.ts

结果：
  alerts 表定义中列名为 status，不是 alert_status
  status: varchar("status", { length: 20 }).notNull().default("open")

步骤 6 — 修复代码：将 alert_status 改为 status
工具调用：执行命令
  sed -i 's/alert_status/status/g' /app/src/routes/alerts.ts

步骤 7 — 确认修复结果
工具调用：执行命令
  sed -n '124,127p' /app/src/routes/alerts.ts

结果：
  124      sql`SELECT COUNT(*)::int AS count FROM alerts
  125          WHERE equipment_id = ${existing[0].equipmentId}
  126          AND status = 'open'`    ← 已修复

步骤 8 — 重启服务使修复生效
工具调用：执行命令
  kill $(pgrep -f "node.*index.ts")

结果：
  进程已终止。entrypoint.sh 的 while true 循环会在 2 秒后自动重启服务。

步骤 9 — 验证服务恢复正常
工具调用：执行命令
  sleep 3 && curl -s http://localhost:3001/api/health

结果：
  {"status":"ok","timestamp":"..."}
  服务已恢复正常运行。
```

### 预期回答

问题已修复！

**根因**：后端 `src/routes/alerts.ts` 第 126 行，在"同步设备状态"的 SQL 查询中使用了错误的列名 `alert_status`，但 alerts 表中该列的实际名称是 `status`。这段逻辑的作用是在处理告警后检查该设备是否还有其他 open 告警，如果没有就把设备状态恢复为 normal。由于列名写错，SQL 执行报错导致整个处理流程失败。

**修复操作**：
1. 定位到 `/app/src/routes/alerts.ts` 第 126 行的错误 SQL
2. 将 `alert_status` 改为 `status`
3. 重启后端服务（entrypoint.sh 自动重启）
4. 验证服务恢复正常

你现在可以再次点击"处理"按钮，应该就能正常处理告警了。
