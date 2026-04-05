import { describe, it, expect, beforeAll, afterAll } from "vitest";
import Docker from "dockerode";
import mysql from "mysql2/promise";
import { mysqlExecutor } from "@/ops-agent/executors/mysql";
import { executeService } from "@/ops-agent/executors/registry";
import { removeContainerIfExists, insertServiceRecord } from "./helpers";

const DOCKER_SOCKET = "/var/run/docker.sock";
const CONTAINER_NAME = "chronos-test-mysql";
const MYSQL_PORT = 23306;
const MYSQL_USER = "root";
const MYSQL_PASS = "test";
const MYSQL_DB = "testdb";

const docker = new Docker({ socketPath: DOCKER_SOCKET });

const connInfo: Record<string, unknown> = {
  host: "127.0.0.1",
  port: MYSQL_PORT,
  username: MYSQL_USER,
  password: MYSQL_PASS,
  database: MYSQL_DB,
};

// ── 种子数据 ──────────────────────────────────────────

const SEED_STATEMENTS = [
  `CREATE TABLE dim_date (
    id INT AUTO_INCREMENT PRIMARY KEY,
    calendar_date DATE NOT NULL UNIQUE,
    year_name VARCHAR(10) NOT NULL,
    week_name VARCHAR(60) NOT NULL,
    day_of_week INT NOT NULL,
    is_weekend TINYINT(1) NOT NULL DEFAULT 0
  )`,
  `CREATE TABLE dim_product (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_code VARCHAR(20) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    sub_class VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    unit_cost DECIMAL(10,2) NOT NULL DEFAULT 0
  )`,
  `CREATE TABLE dim_sell_type (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sell_code VARCHAR(20) NOT NULL UNIQUE,
    sell_name VARCHAR(50) NOT NULL
  )`,
  `CREATE TABLE dim_occasion (
    id INT AUTO_INCREMENT PRIMARY KEY,
    occasion_code VARCHAR(20) NOT NULL UNIQUE,
    occasion_name VARCHAR(50) NOT NULL
  )`,
  `CREATE TABLE dim_store (
    id INT AUTO_INCREMENT PRIMARY KEY,
    store_code VARCHAR(20) NOT NULL UNIQUE,
    store_name VARCHAR(100) NOT NULL,
    city VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    open_date DATE NOT NULL
  )`,
  `CREATE TABLE employees (
    id INT PRIMARY KEY,
    emp_name VARCHAR(50) NOT NULL,
    manager_id INT,
    department VARCHAR(50) NOT NULL,
    salary DECIMAL(10,2) NOT NULL,
    hire_date DATE NOT NULL,
    FOREIGN KEY (manager_id) REFERENCES employees(id)
  )`,
  `CREATE TABLE fact_sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bizdate DATE NOT NULL,
    item_code VARCHAR(20) NOT NULL,
    sell_code VARCHAR(20) NOT NULL,
    occasion_code VARCHAR(20) NOT NULL,
    store_code VARCHAR(20) NOT NULL DEFAULT 'ST01',
    cost_vat DECIMAL(12,2) NOT NULL,
    quantity INT NOT NULL,
    revenue DECIMAL(12,2) NOT NULL
  )`,

  // ── 维度数据 ──
  `INSERT INTO dim_date (calendar_date, year_name, week_name, day_of_week, is_weekend) VALUES
    ('2026-03-23', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 1, 0),
    ('2026-03-24', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 2, 0),
    ('2026-03-25', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 3, 0),
    ('2026-03-26', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 4, 0),
    ('2026-03-27', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 5, 0),
    ('2026-03-28', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 6, 1),
    ('2026-03-29', 'Y2026', 'W13(2026-03-23 - 2026-03-29)', 7, 1),
    ('2026-03-30', 'Y2026', 'W14(2026-03-30 - 2026-04-05)', 1, 0),
    ('2026-03-31', 'Y2026', 'W14(2026-03-30 - 2026-04-05)', 2, 0),
    ('2026-04-01', 'Y2026', 'W14(2026-03-30 - 2026-04-05)', 3, 0)`,

  `INSERT INTO dim_product (item_code, product_name, sub_class, category, unit_cost) VALUES
    ('P001', '水牛乳清甜拿铁', '水牛乳清甜拿铁', '咖啡', 8.50),
    ('P002', '美式咖啡',       '美式咖啡',       '咖啡', 5.00),
    ('P003', '芒果冰沙',       '芒果冰沙',       '果饮', 7.00),
    ('P004', '抹茶拿铁',       '抹茶拿铁',       '茶饮', 9.00),
    ('P005', '柠檬气泡水',     '柠檬气泡水',     '果饮', 3.00),
    ('P006', '燕麦拿铁',       '燕麦拿铁',       '咖啡', 9.50)`,

  `INSERT INTO dim_sell_type (sell_code, sell_name) VALUES ('S01','正价'),('S02','折扣'),('S03','会员价')`,
  `INSERT INTO dim_occasion (occasion_code, occasion_name) VALUES ('OC01','Delivery'),('OC02','Dine-in'),('OC03','Takeaway')`,

  `INSERT INTO dim_store (store_code, store_name, city, region, open_date) VALUES
    ('ST01','南京西路旗舰店','上海','华东','2024-01-15'),
    ('ST02','国贸中心店','北京','华北','2024-03-01'),
    ('ST03','天河城店','广州','华南','2024-06-20'),
    ('ST04','湖滨银泰店','杭州','华东','2025-01-10'),
    ('ST05','春熙路店','成都','西南','2025-04-01')`,

  `INSERT INTO employees (id, emp_name, manager_id, department, salary, hire_date) VALUES
    (1, '张总',   NULL, '管理层', 50000, '2020-01-01'),
    (2, '李VP',   1,    '运营部', 35000, '2020-06-01'),
    (3, '王VP',   1,    '技术部', 38000, '2020-06-15'),
    (4, '赵经理', 2,    '运营部', 25000, '2021-03-01'),
    (5, '钱经理', 2,    '运营部', 24000, '2021-05-01'),
    (6, '孙经理', 3,    '技术部', 28000, '2021-04-01'),
    (7, '周员工', 4,    '运营部', 15000, '2022-01-15'),
    (8, '吴员工', 4,    '运营部', 14000, '2022-03-01'),
    (9, '郑员工', 5,    '运营部', 13500, '2022-06-01'),
    (10,'冯员工', 6,    '技术部', 18000, '2022-02-01'),
    (11,'陈员工', 6,    '技术部', 17500, '2022-07-01'),
    (12,'卫实习', 7,    '运营部', 6000,  '2025-09-01')`,

  // ── 事实数据 ──
  `INSERT INTO fact_sales (bizdate, item_code, sell_code, occasion_code, store_code, cost_vat, quantity, revenue) VALUES
    ('2026-03-23','P001','S01','OC01','ST01',25.50,10,320.00),
    ('2026-03-23','P001','S01','OC02','ST01',22.00,9,288.00),
    ('2026-03-23','P002','S01','OC01','ST01',12.00,15,225.00),
    ('2026-03-23','P003','S01','OC03','ST02',20.00,7,210.00),
    ('2026-03-23','P004','S01','OC02','ST02',28.00,11,330.00),
    ('2026-03-23','P005','S02','OC03','ST03',5.00,20,120.00),
    ('2026-03-23','P006','S01','OC01','ST03',30.00,8,256.00),
    ('2026-03-24','P001','S01','OC01','ST01',30.00,12,384.00),
    ('2026-03-24','P001','S03','OC02','ST04',15.50,6,180.00),
    ('2026-03-24','P002','S02','OC01','ST01',10.50,11,165.00),
    ('2026-03-24','P003','S02','OC03','ST02',16.00,5,150.00),
    ('2026-03-24','P005','S01','OC02','ST04',6.00,18,126.00),
    ('2026-03-24','P006','S03','OC01','ST05',22.00,10,280.00),
    ('2026-03-25','P001','S02','OC01','ST01',18.00,8,240.00),
    ('2026-03-25','P002','S01','OC03','ST01',14.00,13,195.00),
    ('2026-03-25','P004','S03','OC02','ST02',19.00,8,240.00),
    ('2026-03-25','P006','S02','OC03','ST03',24.00,6,180.00),
    ('2026-03-26','P001','S01','OC01','ST04',26.00,11,352.00),
    ('2026-03-26','P002','S01','OC02','ST05',13.00,14,210.00),
    ('2026-03-26','P003','S01','OC01','ST03',21.00,9,252.00),
    ('2026-03-26','P005','S02','OC03','ST01',4.50,25,150.00),
    ('2026-03-27','P001','S01','OC01','ST01',28.00,13,416.00),
    ('2026-03-27','P004','S01','OC02','ST02',32.00,12,360.00),
    ('2026-03-27','P006','S01','OC01','ST05',33.00,11,352.00),
    ('2026-03-28','P001','S01','OC02','ST01',35.00,18,576.00),
    ('2026-03-28','P002','S01','OC03','ST01',16.00,20,300.00),
    ('2026-03-28','P003','S01','OC01','ST03',24.00,12,336.00),
    ('2026-03-28','P004','S02','OC02','ST02',25.00,15,375.00),
    ('2026-03-28','P006','S01','OC03','ST04',28.00,14,392.00),
    ('2026-03-29','P001','S02','OC01','ST01',20.00,15,450.00),
    ('2026-03-29','P002','S01','OC02','ST05',15.00,17,255.00),
    ('2026-03-29','P005','S01','OC03','ST04',7.00,22,154.00),
    ('2026-03-29','P003','S01','OC02','ST03',22.00,10,280.00),
    ('2026-03-30','P001','S01','OC01','ST01',35.00,14,448.00),
    ('2026-03-31','P002','S02','OC02','ST02',11.00,9,135.00),
    ('2026-04-01','P004','S01','OC01','ST03',30.00,10,300.00)`,
];

const TOTAL_FACT_ROWS = 36;
const EXPECTED_LATTE_DELIVERY_W13_COST = "147.50";

async function waitForMySQL(timeoutMs = 90_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const conn = await mysql.createConnection({
        host: "127.0.0.1", port: MYSQL_PORT, user: MYSQL_USER,
        password: MYSQL_PASS, database: MYSQL_DB, connectTimeout: 3000,
      });
      await conn.query("SELECT 1");
      await conn.end();
      return;
    } catch {
      await Bun.sleep(2000);
    }
  }
  throw new Error(`waitForMySQL: not ready after ${timeoutMs}ms`);
}

describe("MySQL Executor", () => {
  beforeAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);

    const container = await docker.createContainer({
      Image: "mysql:8.0",
      name: CONTAINER_NAME,
      Env: [`MYSQL_ROOT_PASSWORD=${MYSQL_PASS}`, `MYSQL_DATABASE=${MYSQL_DB}`],
      HostConfig: {
        PortBindings: { "3306/tcp": [{ HostPort: String(MYSQL_PORT) }] },
      },
    });
    await container.start();
    await waitForMySQL(90_000);

    const conn = await mysql.createConnection({
      host: "127.0.0.1", port: MYSQL_PORT, user: MYSQL_USER,
      password: MYSQL_PASS, database: MYSQL_DB,
    });
    for (const stmt of SEED_STATEMENTS) {
      await conn.query(stmt);
    }
    await conn.end();
  }, 120_000);

  afterAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);
  });

  // ── 基础复杂查询 ────────────────────────────────────

  describe("executeSql — 多表 JOIN 聚合", () => {
    it("5 表 LEFT JOIN + SUM (BI 查询)", async () => {
      const query = `
        SELECT SUM(a.cost_vat) as total_cost
        FROM fact_sales a
        LEFT JOIN dim_date b ON a.bizdate = b.calendar_date
        LEFT JOIN dim_sell_type c ON a.sell_code = c.sell_code
        LEFT JOIN dim_product d ON a.item_code = d.item_code
        LEFT JOIN dim_occasion e ON a.occasion_code = e.occasion_code
        WHERE b.year_name = 'Y2026'
          AND b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          AND d.sub_class = '水牛乳清甜拿铁'
          AND e.occasion_name = 'Delivery'
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ total_cost: string }>;
      expect(rows).toHaveLength(1);
      expect(rows[0].total_cost).toBe(EXPECTED_LATTE_DELIVERY_W13_COST);
    });

    it("6 表 JOIN + GROUP BY 多维", async () => {
      const query = `
        SELECT s.region, d.category, e.occasion_name,
               SUM(a.revenue) as total_revenue,
               SUM(a.quantity) as total_qty
        FROM fact_sales a
        JOIN dim_date b ON a.bizdate = b.calendar_date
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_sell_type c ON a.sell_code = c.sell_code
        JOIN dim_occasion e ON a.occasion_code = e.occasion_code
        JOIN dim_store s ON a.store_code = s.store_code
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          AND s.region = '华东'
        GROUP BY s.region, d.category, e.occasion_name
        ORDER BY total_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, unknown>>;
      expect(rows.length).toBeGreaterThan(0);
      for (const r of rows) expect(r.region).toBe("华东");
    });

    it("GROUP BY + HAVING + AVG", async () => {
      const query = `
        SELECT d.sub_class,
               COUNT(*) as order_count,
               SUM(a.revenue) as total_revenue,
               ROUND(AVG(a.revenue / a.quantity), 2) as avg_unit_price
        FROM fact_sales a
        JOIN dim_date b ON a.bizdate = b.calendar_date
        JOIN dim_product d ON a.item_code = d.item_code
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.sub_class
        HAVING SUM(a.revenue) > 500
        ORDER BY total_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ sub_class: string; total_revenue: string }>;
      for (const r of rows) expect(Number(r.total_revenue)).toBeGreaterThan(500);
      expect(rows[0].sub_class).toBe("水牛乳清甜拿铁");
    });
  });

  // ── CTE 查询 ────────────────────────────────────────

  describe("executeSql — CTE (WITH)", () => {
    it("单层 CTE + Top N", async () => {
      const query = `
        WITH product_summary AS (
          SELECT d.item_code, d.product_name, d.category,
                 SUM(a.revenue) as total_revenue,
                 SUM(a.quantity) as total_qty
          FROM fact_sales a
          JOIN dim_product d ON a.item_code = d.item_code
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY d.item_code, d.product_name, d.category
        )
        SELECT product_name, category, total_revenue, total_qty,
               ROUND(total_revenue / total_qty, 2) as avg_price
        FROM product_summary
        ORDER BY total_revenue DESC
        LIMIT 3
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(3);
      expect(Number(rows[0].total_revenue)).toBeGreaterThanOrEqual(Number(rows[1].total_revenue));
    });

    it("多层 CTE: 产品 → 类目 → 占比", async () => {
      const query = `
        WITH product_agg AS (
          SELECT d.item_code, d.category, SUM(a.revenue) as revenue
          FROM fact_sales a
          JOIN dim_product d ON a.item_code = d.item_code
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY d.item_code, d.category
        ),
        category_agg AS (
          SELECT category, SUM(revenue) as cat_revenue
          FROM product_agg
          GROUP BY category
        ),
        grand_total AS (
          SELECT SUM(cat_revenue) as total FROM category_agg
        )
        SELECT c.category, c.cat_revenue,
               ROUND(c.cat_revenue * 100.0 / g.total, 2) as pct
        FROM category_agg c
        CROSS JOIN grand_total g
        ORDER BY c.cat_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ pct: string }>;
      const totalPct = rows.reduce((s, r) => s + Number(r.pct), 0);
      expect(totalPct).toBeCloseTo(100, 0);
    });

    it("CTE + JOIN: 门店日均 vs 全网日均对比", async () => {
      const query = `
        WITH store_daily AS (
          SELECT a.store_code, a.bizdate, SUM(a.revenue) as daily_rev
          FROM fact_sales a
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY a.store_code, a.bizdate
        ),
        store_avg AS (
          SELECT store_code, ROUND(AVG(daily_rev), 2) as avg_daily_rev
          FROM store_daily GROUP BY store_code
        ),
        network_avg AS (
          SELECT ROUND(AVG(daily_rev), 2) as network_avg FROM store_daily
        )
        SELECT s.store_name, sa.avg_daily_rev, n.network_avg,
               IF(sa.avg_daily_rev > n.network_avg, '高于均值', '低于均值') as performance
        FROM store_avg sa
        JOIN dim_store s ON sa.store_code = s.store_code
        CROSS JOIN network_avg n
        ORDER BY sa.avg_daily_rev DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, unknown>>;
      expect(rows.length).toBeGreaterThan(0);
      const hi = rows.filter((r) => r.performance === "高于均值");
      const lo = rows.filter((r) => r.performance === "低于均值");
      expect(hi.length + lo.length).toBe(rows.length);
    });
  });

  // ── 递归 CTE ────────────────────────────────────────

  describe("executeSql — 递归 CTE", () => {
    it("递归遍历员工层级树", async () => {
      const query = `
        WITH RECURSIVE org_tree AS (
          SELECT id, emp_name, manager_id, department, salary, 1 as depth,
                 CAST(emp_name AS CHAR(500)) as path
          FROM employees
          WHERE manager_id IS NULL
          UNION ALL
          SELECT e.id, e.emp_name, e.manager_id, e.department, e.salary,
                 t.depth + 1,
                 CONCAT(t.path, ' → ', e.emp_name)
          FROM employees e
          JOIN org_tree t ON e.manager_id = t.id
        )
        SELECT id, emp_name, depth, path, department, salary
        FROM org_tree
        ORDER BY depth, salary DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        emp_name: string; depth: number; path: string;
      }>;
      expect(rows[0].emp_name).toBe("张总");
      expect(rows[0].depth).toBe(1);
      const intern = rows.find((r) => r.emp_name === "卫实习");
      expect(intern).toBeDefined();
      expect(intern!.depth).toBe(5);
      expect(rows.length).toBe(12);
    });
  });

  // ── 窗口函数 ────────────────────────────────────────

  describe("executeSql — 窗口函数", () => {
    it("ROW_NUMBER + RANK + DENSE_RANK", async () => {
      const query = `
        SELECT d.product_name,
               SUM(a.revenue) as total_revenue,
               ROW_NUMBER() OVER (ORDER BY SUM(a.revenue) DESC) as rn,
               RANK()        OVER (ORDER BY SUM(a.revenue) DESC) as rnk,
               DENSE_RANK()  OVER (ORDER BY SUM(a.revenue) DESC) as drnk
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.product_name
        ORDER BY rn
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ rn: number }>;
      expect(rows.length).toBe(6);
      expect(rows[0].rn).toBe(1);
    });

    it("LAG + LEAD: 逐日营收环比", async () => {
      const query = `
        WITH daily AS (
          SELECT a.bizdate, SUM(a.revenue) as day_revenue
          FROM fact_sales a
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY a.bizdate
        )
        SELECT bizdate, day_revenue,
               LAG(day_revenue, 1) OVER (ORDER BY bizdate) as prev_day,
               LEAD(day_revenue, 1) OVER (ORDER BY bizdate) as next_day,
               day_revenue - LAG(day_revenue, 1) OVER (ORDER BY bizdate) as day_over_day
        FROM daily
        ORDER BY bizdate
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, unknown>>;
      expect(rows.length).toBe(7);
      expect(rows[0].prev_day).toBeNull();
      expect(rows[rows.length - 1].next_day).toBeNull();
    });

    it("SUM OVER: 累计求和 running total", async () => {
      const query = `
        WITH daily AS (
          SELECT a.bizdate, SUM(a.revenue) as day_revenue
          FROM fact_sales a
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY a.bizdate
        )
        SELECT bizdate, day_revenue,
               SUM(day_revenue) OVER (ORDER BY bizdate ROWS UNBOUNDED PRECEDING) as running_total
        FROM daily ORDER BY bizdate
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        day_revenue: string; running_total: string;
      }>;
      const totalRev = rows.reduce((s, r) => s + Number(r.day_revenue), 0);
      expect(Number(rows[rows.length - 1].running_total)).toBeCloseTo(totalRev, 2);
    });

    it("PARTITION BY + Top 1 per group", async () => {
      const query = `
        WITH ranked AS (
          SELECT d.category, d.product_name,
                 SUM(a.revenue) as total_revenue,
                 ROW_NUMBER() OVER (PARTITION BY d.category ORDER BY SUM(a.revenue) DESC) as rn
          FROM fact_sales a
          JOIN dim_product d ON a.item_code = d.item_code
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY d.category, d.product_name
        )
        SELECT category, product_name, total_revenue
        FROM ranked WHERE rn = 1
        ORDER BY total_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ category: string }>;
      expect(rows.length).toBe(3);
      expect(rows.map((r) => r.category)).toContain("咖啡");
    });

    it("AVG OVER: 3 日滑动平均", async () => {
      const query = `
        WITH daily AS (
          SELECT a.bizdate, SUM(a.revenue) as day_revenue
          FROM fact_sales a
          JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY a.bizdate
        )
        SELECT bizdate, day_revenue,
               ROUND(AVG(day_revenue) OVER (
                 ORDER BY bizdate ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
               ), 2) as moving_avg_3d
        FROM daily ORDER BY bizdate
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        day_revenue: string; moving_avg_3d: string;
      }>;
      expect(rows.length).toBe(7);
      const mid = 3;
      const expected = (Number(rows[mid - 1].day_revenue) + Number(rows[mid].day_revenue) + Number(rows[mid + 1].day_revenue)) / 3;
      expect(Number(rows[mid].moving_avg_3d)).toBeCloseTo(expected, 1);
    });
  });

  // ── CASE WHEN / 透视 ───────────────────────────────

  describe("executeSql — CASE WHEN 透视 & 条件聚合", () => {
    it("行转列透视: occasion 分列", async () => {
      const query = `
        SELECT d.product_name,
               SUM(CASE WHEN e.occasion_name = 'Delivery'  THEN a.revenue ELSE 0 END) as delivery_rev,
               SUM(CASE WHEN e.occasion_name = 'Dine-in'   THEN a.revenue ELSE 0 END) as dinein_rev,
               SUM(CASE WHEN e.occasion_name = 'Takeaway'  THEN a.revenue ELSE 0 END) as takeaway_rev,
               SUM(a.revenue) as total_rev
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_occasion e ON a.occasion_code = e.occasion_code
        JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.product_name ORDER BY total_rev DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        delivery_rev: string; dinein_rev: string; takeaway_rev: string; total_rev: string;
      }>;
      expect(rows.length).toBe(6);
      for (const r of rows) {
        const sum = Number(r.delivery_rev) + Number(r.dinein_rev) + Number(r.takeaway_rev);
        expect(sum).toBeCloseTo(Number(r.total_rev), 2);
      }
    });

    it("工作日 vs 周末对比", async () => {
      const query = `
        SELECT d.category,
               SUM(IF(b.is_weekend, a.revenue, 0)) as weekend_rev,
               SUM(IF(NOT b.is_weekend, a.revenue, 0)) as weekday_rev,
               ROUND(SUM(IF(b.is_weekend, a.revenue, 0)) * 100.0 / SUM(a.revenue), 2) as weekend_pct
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.category ORDER BY weekend_pct DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ weekend_pct: string }>;
      expect(rows.length).toBe(3);
      for (const r of rows) {
        expect(Number(r.weekend_pct)).toBeGreaterThanOrEqual(0);
        expect(Number(r.weekend_pct)).toBeLessThanOrEqual(100);
      }
    });

    it("CASE WHEN 分桶", async () => {
      const query = `
        SELECT price_tier, COUNT(*) as product_count, ROUND(AVG(total_revenue), 2) as avg_revenue
        FROM (
          SELECT d.item_code,
                 ROUND(SUM(a.revenue) / SUM(a.quantity), 2) as avg_unit_price,
                 SUM(a.revenue) as total_revenue,
                 CASE
                   WHEN ROUND(SUM(a.revenue) / SUM(a.quantity), 2) < 15 THEN '低客单 (<15)'
                   WHEN ROUND(SUM(a.revenue) / SUM(a.quantity), 2) < 25 THEN '中客单 (15-25)'
                   ELSE '高客单 (>=25)'
                 END as price_tier
          FROM fact_sales a JOIN dim_product d ON a.item_code = d.item_code
          GROUP BY d.item_code
        ) sub
        GROUP BY price_tier ORDER BY avg_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ product_count: number }>;
      const total = rows.reduce((s, r) => s + Number(r.product_count), 0);
      expect(total).toBe(6);
    });
  });

  // ── 子查询 / EXISTS ────────────────────────────────

  describe("executeSql — 子查询 & EXISTS", () => {
    it("关联子查询: 每产品最大单日营收", async () => {
      const query = `
        SELECT d.product_name, a.bizdate, a.revenue
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        WHERE a.revenue = (
          SELECT MAX(a2.revenue) FROM fact_sales a2 WHERE a2.item_code = a.item_code
        )
        ORDER BY a.revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, unknown>>;
      expect(rows.length).toBeGreaterThanOrEqual(6);
    });

    it("EXISTS: W13 有 Delivery 的门店", async () => {
      const query = `
        SELECT s.store_name, s.city
        FROM dim_store s
        WHERE EXISTS (
          SELECT 1 FROM fact_sales a
          JOIN dim_date b ON a.bizdate = b.calendar_date
          JOIN dim_occasion e ON a.occasion_code = e.occasion_code
          WHERE a.store_code = s.store_code
            AND b.week_name = 'W13(2026-03-23 - 2026-03-29)'
            AND e.occasion_name = 'Delivery'
        )
        ORDER BY s.store_name
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ store_name: string }>;
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.map((r) => r.store_name)).toContain("南京西路旗舰店");
    });

    it("标量子查询 in SELECT: 每行附带全局总和和占比", async () => {
      const query = `
        SELECT d.product_name,
               SUM(a.revenue) as prod_revenue,
               (SELECT SUM(f.revenue) FROM fact_sales f
                JOIN dim_date dd ON f.bizdate = dd.calendar_date
                WHERE dd.week_name = 'W13(2026-03-23 - 2026-03-29)') as grand_total,
               ROUND(SUM(a.revenue) * 100.0 / (
                 SELECT SUM(f.revenue) FROM fact_sales f
                 JOIN dim_date dd ON f.bizdate = dd.calendar_date
                 WHERE dd.week_name = 'W13(2026-03-23 - 2026-03-29)'
               ), 2) as pct_of_total
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.product_name ORDER BY pct_of_total DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ pct_of_total: string }>;
      const totalPct = rows.reduce((s, r) => s + Number(r.pct_of_total), 0);
      expect(totalPct).toBeCloseTo(100, 0);
    });
  });

  // ── UNION ──────────────────────────────────────────

  describe("executeSql — UNION", () => {
    it("UNION ALL: 工作日 vs 周末汇总", async () => {
      const query = `
        SELECT '工作日' as period, SUM(a.revenue) as total_revenue, COUNT(*) as cnt
        FROM fact_sales a JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)' AND NOT b.is_weekend
        UNION ALL
        SELECT '周末', SUM(a.revenue), COUNT(*)
        FROM fact_sales a JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)' AND b.is_weekend
        ORDER BY period
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ period: string }>;
      expect(rows).toHaveLength(2);
      expect(rows.map((r) => r.period)).toContain("工作日");
    });
  });

  // ── MySQL 特有语法 ────────────────────────────────

  describe("executeSql — MySQL 特有语法", () => {
    it("IF / IFNULL / COALESCE", async () => {
      const query = `
        SELECT d.product_name,
               SUM(a.revenue) as total_revenue,
               IF(SUM(a.revenue) > 500, '高', '低') as level,
               IFNULL(NULL, '默认值') as test_ifnull,
               COALESCE(NULL, NULL, '兜底') as test_coalesce
        FROM fact_sales a JOIN dim_product d ON a.item_code = d.item_code
        GROUP BY d.product_name ORDER BY total_revenue DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<Record<string, string>>;
      const latte = rows.find((r) => r.product_name === "水牛乳清甜拿铁");
      expect(latte?.level).toBe("高");
      expect(rows[0].test_ifnull).toBe("默认值");
      expect(rows[0].test_coalesce).toBe("兜底");
    });

    it("GROUP_CONCAT: 聚合为字符串", async () => {
      const query = `
        SELECT d.category,
               GROUP_CONCAT(DISTINCT d.product_name ORDER BY d.product_name SEPARATOR ', ') as products
        FROM dim_product d
        GROUP BY d.category
        ORDER BY d.category
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        category: string; products: string;
      }>;
      const coffee = rows.find((r) => r.category === "咖啡");
      expect(coffee).toBeDefined();
      expect(coffee!.products).toContain("美式咖啡");
      expect(coffee!.products.split(", ").length).toBe(3);
    });

    it("DATE_FORMAT + DATEDIFF + 日期函数", async () => {
      const query = `
        SELECT s.store_name,
               s.open_date,
               DATE_FORMAT(s.open_date, '%Y年%m月') as open_month,
               DATEDIFF('2026-03-23', s.open_date) as days_since_open,
               TIMESTAMPDIFF(MONTH, s.open_date, '2026-03-23') as months_since_open
        FROM dim_store s
        ORDER BY days_since_open DESC
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        store_name: string; days_since_open: number; months_since_open: number;
      }>;
      expect(rows.length).toBe(5);
      // 最早开店的 days_since_open 最大
      expect(Number(rows[0].days_since_open)).toBeGreaterThan(Number(rows[rows.length - 1].days_since_open));
    });

    it("WITH ROLLUP: 分组 + 小计 + 总计", async () => {
      const query = `
        SELECT
          IFNULL(d.category, '【总计】') as category,
          IFNULL(e.occasion_name, '【小计】') as occasion,
          SUM(a.revenue) as revenue
        FROM fact_sales a
        JOIN dim_product d ON a.item_code = d.item_code
        JOIN dim_occasion e ON a.occasion_code = e.occasion_code
        JOIN dim_date b ON a.bizdate = b.calendar_date
        WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        GROUP BY d.category, e.occasion_name WITH ROLLUP
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        category: string; occasion: string; revenue: string;
      }>;
      // 最后一行应该是总计
      const lastRow = rows[rows.length - 1];
      expect(lastRow.category).toBe("【总计】");
      expect(lastRow.occasion).toBe("【小计】");
      // 总计行的 revenue 应等于所有具体行 revenue 之和
      const detailRows = rows.filter((r) => r.category !== "【总计】" && r.occasion !== "【小计】");
      const detailSum = detailRows.reduce((s, r) => s + Number(r.revenue), 0);
      expect(Number(lastRow.revenue)).toBeCloseTo(detailSum, 2);
    });
  });

  // ── 超复杂组合查询 ────────────────────────────────

  describe("executeSql — 超复杂组合查询", () => {
    it("CTE + 窗口 + CASE WHEN + 多层嵌套: 门店报表", async () => {
      const query = `
        WITH daily_store AS (
          SELECT a.store_code, a.bizdate, SUM(a.revenue) as daily_rev, SUM(a.quantity) as daily_qty
          FROM fact_sales a JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
          GROUP BY a.store_code, a.bizdate
        ),
        store_metrics AS (
          SELECT store_code,
                 SUM(daily_rev) as total_rev,
                 ROUND(AVG(daily_rev), 2) as avg_daily_rev,
                 MAX(daily_rev) as peak_day_rev,
                 MIN(daily_rev) as trough_day_rev,
                 COUNT(*) as active_days
          FROM daily_store GROUP BY store_code
        ),
        ranked AS (
          SELECT sm.*, s.store_name, s.city, s.region,
                 RANK() OVER (ORDER BY sm.total_rev DESC) as revenue_rank,
                 ROUND(sm.total_rev * 100.0 / SUM(sm.total_rev) OVER (), 2) as pct_of_total
          FROM store_metrics sm
          JOIN dim_store s ON sm.store_code = s.store_code
        )
        SELECT store_name, city, region, total_rev, avg_daily_rev, revenue_rank, pct_of_total,
               CASE
                 WHEN revenue_rank = 1 THEN '冠军门店'
                 WHEN pct_of_total >= 20 THEN '核心门店'
                 WHEN pct_of_total >= 10 THEN '成长门店'
                 ELSE '观察门店'
               END as store_tier
        FROM ranked ORDER BY revenue_rank
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        revenue_rank: number; store_tier: string; pct_of_total: string;
      }>;
      expect(rows.length).toBe(5);
      expect(rows[0].revenue_rank).toBe(1);
      expect(rows[0].store_tier).toBe("冠军门店");
      const totalPct = rows.reduce((s, r) => s + Number(r.pct_of_total), 0);
      expect(totalPct).toBeCloseTo(100, 0);
    });

    it("递归 CTE + 窗口: 组织架构薪资分析", async () => {
      const query = `
        WITH RECURSIVE org AS (
          SELECT id, emp_name, manager_id, department, salary, 1 as depth
          FROM employees WHERE manager_id IS NULL
          UNION ALL
          SELECT e.id, e.emp_name, e.manager_id, e.department, e.salary, o.depth + 1
          FROM employees e JOIN org o ON e.manager_id = o.id
        ),
        dept_stats AS (
          SELECT department,
                 COUNT(*) as head_count,
                 SUM(salary) as total_salary,
                 ROUND(AVG(salary), 2) as avg_salary,
                 MAX(salary) as max_salary,
                 MIN(salary) as min_salary
          FROM org GROUP BY department
        )
        SELECT department, head_count, total_salary, avg_salary,
               max_salary - min_salary as salary_spread,
               RANK() OVER (ORDER BY avg_salary DESC) as avg_salary_rank
        FROM dept_stats ORDER BY avg_salary_rank
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{ head_count: number }>;
      expect(rows.length).toBeGreaterThan(0);
      const totalHead = rows.reduce((s, r) => s + Number(r.head_count), 0);
      expect(totalHead).toBe(12);
    });

    it("多 CTE + UNION + 窗口: 综合仪表板", async () => {
      const query = `
        WITH w13_sales AS (
          SELECT a.item_code, a.store_code, a.occasion_code, a.bizdate,
                 a.revenue, a.quantity, a.cost_vat
          FROM fact_sales a JOIN dim_date b ON a.bizdate = b.calendar_date
          WHERE b.week_name = 'W13(2026-03-23 - 2026-03-29)'
        ),
        kpi_by_product AS (
          SELECT 'product' as dimension, d.product_name as dim_value,
                 SUM(w.revenue) as revenue, SUM(w.quantity) as qty,
                 ROUND(SUM(w.revenue) / SUM(w.quantity), 2) as avg_price
          FROM w13_sales w JOIN dim_product d ON w.item_code = d.item_code
          GROUP BY d.product_name
        ),
        kpi_by_store AS (
          SELECT 'store' as dimension, s.store_name as dim_value,
                 SUM(w.revenue) as revenue, SUM(w.quantity) as qty,
                 ROUND(SUM(w.revenue) / SUM(w.quantity), 2) as avg_price
          FROM w13_sales w JOIN dim_store s ON w.store_code = s.store_code
          GROUP BY s.store_name
        ),
        combined AS (
          SELECT * FROM kpi_by_product UNION ALL SELECT * FROM kpi_by_store
        )
        SELECT dimension, dim_value, revenue, qty, avg_price,
               RANK() OVER (PARTITION BY dimension ORDER BY revenue DESC) as rank_in_dim
        FROM combined ORDER BY dimension, rank_in_dim
      `;
      const rows = (await mysqlExecutor(connInfo, "executeSql", { query })) as Array<{
        dimension: string; rank_in_dim: number;
      }>;
      const products = rows.filter((r) => r.dimension === "product");
      const stores = rows.filter((r) => r.dimension === "store");
      expect(products.length).toBe(6);
      expect(stores.length).toBe(5);
    });
  });

  // ── 元数据操作 ────────────────────────────────────────

  describe("元数据操作", () => {
    it("listDatabases", async () => {
      const rows = (await mysqlExecutor(connInfo, "listDatabases", {})) as Array<{ Database: string }>;
      expect(rows.map((r) => r.Database)).toContain(MYSQL_DB);
    });

    it("listTables", async () => {
      const rows = (await mysqlExecutor(connInfo, "listTables", { schema: MYSQL_DB })) as Array<Record<string, string>>;
      const names = rows.map((r) => r.TABLE_NAME || r.table_name);
      expect(names).toContain("dim_date");
      expect(names).toContain("fact_sales");
      expect(names).toContain("employees");
    });

    it("describeTable", async () => {
      const rows = (await mysqlExecutor(connInfo, "describeTable", { table: "fact_sales" })) as Array<Record<string, string>>;
      const colNames = rows.map((r) => r.COLUMN_NAME || r.column_name);
      expect(colNames).toContain("store_code");
      expect(colNames).toContain("cost_vat");
    });

    it("tableRowCount", async () => {
      const rows = (await mysqlExecutor(connInfo, "tableRowCount", { table: "fact_sales" })) as Array<{ count: number }>;
      expect(Number(rows[0].count)).toBe(TOTAL_FACT_ROWS);
    });
  });

  // ── executeService 端到端 ──────────────────────────

  describe("executeService 端到端", () => {
    it("注册 MySQL service 并执行复杂查询", async () => {
      const serviceId = await insertServiceRecord({
        name: "test-mysql-exec",
        serviceType: "mysql",
        host: "127.0.0.1",
        port: MYSQL_PORT,
        config: { username: MYSQL_USER, password: MYSQL_PASS, database: MYSQL_DB },
      });
      const rows = (await executeService(serviceId, "executeSql", {
        query: `
          WITH s AS (SELECT store_code, SUM(revenue) as rev FROM fact_sales GROUP BY store_code)
          SELECT COUNT(*) as cnt FROM s WHERE rev > 500
        `,
      })) as Array<{ cnt: number }>;
      expect(Number(rows[0].cnt)).toBeGreaterThan(0);
    });
  });

  // ── 错误处理 ──────────────────────────────────────────

  describe("错误处理", () => {
    it("空 query 报错", async () => {
      await expect(mysqlExecutor(connInfo, "executeSql", {})).rejects.toThrow("参数 query 不能为空");
    });

    it("不支持的 operation 报错", async () => {
      await expect(mysqlExecutor(connInfo, "unknownOp", {})).rejects.toThrow('unsupported operation "unknownOp"');
    });

    it("语法错误 SQL 报错", async () => {
      await expect(mysqlExecutor(connInfo, "executeSql", { query: "SELEC * FORM x" })).rejects.toThrow();
    });

    it("引用不存在的表报错", async () => {
      await expect(mysqlExecutor(connInfo, "executeSql", { query: "SELECT * FROM ghost_table" })).rejects.toThrow();
    });
  });
});
