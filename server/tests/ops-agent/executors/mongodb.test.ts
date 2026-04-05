import { describe, it, expect, beforeAll, afterAll } from "vitest";
import Docker from "dockerode";
import { MongoClient } from "mongodb";
import { mongoExecutor } from "@/ops-agent/executors/mongodb";
import { executeService } from "@/ops-agent/executors/registry";
import {
  waitForMongo,
  removeContainerIfExists,
  insertServiceRecord,
} from "./helpers";

const DOCKER_SOCKET = "/var/run/docker.sock";
const CONTAINER_NAME = "chronos-test-mongo";
const MONGO_PORT = 27018;
const MONGO_URI = `mongodb://127.0.0.1:${MONGO_PORT}`;
const TEST_DB = "testdb";

const docker = new Docker({ socketPath: DOCKER_SOCKET });

const connInfo: Record<string, unknown> = {
  host: "127.0.0.1",
  port: MONGO_PORT,
};

// ── 种子数据 ──────────────────────────────────────────

const CUSTOMERS = [
  { customerId: "C001", name: "张三", email: "zhang@test.com", tier: "gold", region: "华东", joinDate: new Date("2024-01-15"), totalSpent: 2500 },
  { customerId: "C002", name: "李四", email: "li@test.com", tier: "silver", region: "华北", joinDate: new Date("2024-03-20"), totalSpent: 1200 },
  { customerId: "C003", name: "王五", email: "wang@test.com", tier: "gold", region: "华南", joinDate: new Date("2024-06-10"), totalSpent: 1800 },
  { customerId: "C004", name: "赵六", email: "zhao@test.com", tier: "bronze", region: "华东", joinDate: new Date("2025-01-05"), totalSpent: 600 },
  { customerId: "C005", name: "钱七", email: "qian@test.com", tier: "silver", region: "华北", joinDate: new Date("2025-04-12"), totalSpent: 900 },
];

const PRODUCTS = [
  { productId: "PRD001", name: "拿铁咖啡", category: "咖啡", subCategory: "经典咖啡", price: 32, stock: 100, cost: 12 },
  { productId: "PRD002", name: "美式咖啡", category: "咖啡", subCategory: "经典咖啡", price: 24, stock: 200, cost: 8 },
  { productId: "PRD003", name: "芒果冰沙", category: "果饮", subCategory: "冰沙", price: 28, stock: 80, cost: 10 },
  { productId: "PRD004", name: "抹茶拿铁", category: "茶饮", subCategory: "奶茶", price: 30, stock: 150, cost: 11 },
  { productId: "PRD005", name: "椰子水", category: "果饮", subCategory: "鲜果饮", price: 18, stock: 300, cost: 5 },
  { productId: "PRD006", name: "燕麦拿铁", category: "咖啡", subCategory: "植物奶咖啡", price: 35, stock: 120, cost: 14 },
];

const STORES = [
  { storeId: "S001", name: "华东总部", region: "华东", city: "上海", parentStoreId: null, openDate: new Date("2023-01-01") },
  { storeId: "S002", name: "南京西路店", region: "华东", city: "上海", parentStoreId: "S001", openDate: new Date("2023-06-15") },
  { storeId: "S003", name: "杭州银泰店", region: "华东", city: "杭州", parentStoreId: "S001", openDate: new Date("2024-01-10") },
  { storeId: "S004", name: "华北总部", region: "华北", city: "北京", parentStoreId: null, openDate: new Date("2023-03-01") },
  { storeId: "S005", name: "国贸中心店", region: "华北", city: "北京", parentStoreId: "S004", openDate: new Date("2024-03-20") },
];

const ORDERS = [
  {
    orderId: "ORD001", customerId: "C001", storeId: "S002", status: "completed", channel: "online",
    total: 120, discount: 0, paymentMethod: "wechat",
    createdAt: new Date("2026-03-23T10:30:00Z"),
    items: [
      { productId: "PRD001", name: "拿铁咖啡", quantity: 2, price: 32 },
      { productId: "PRD003", name: "芒果冰沙", quantity: 2, price: 28 },
    ],
  },
  {
    orderId: "ORD002", customerId: "C002", storeId: "S005", status: "completed", channel: "app",
    total: 88, discount: 10, paymentMethod: "alipay",
    createdAt: new Date("2026-03-23T14:00:00Z"),
    items: [
      { productId: "PRD002", name: "美式咖啡", quantity: 2, price: 24 },
      { productId: "PRD004", name: "抹茶拿铁", quantity: 1, price: 30 },
      { productId: "PRD005", name: "椰子水", quantity: 1, price: 18 },
    ],
  },
  {
    orderId: "ORD003", customerId: "C001", storeId: "S002", status: "completed", channel: "online",
    total: 210, discount: 20, paymentMethod: "wechat",
    createdAt: new Date("2026-03-24T09:15:00Z"),
    items: [
      { productId: "PRD001", name: "拿铁咖啡", quantity: 5, price: 32 },
      { productId: "PRD002", name: "美式咖啡", quantity: 2, price: 24 },
    ],
  },
  {
    orderId: "ORD004", customerId: "C003", storeId: "S003", status: "pending", channel: "store",
    total: 56, discount: 0, paymentMethod: "cash",
    createdAt: new Date("2026-03-24T16:45:00Z"),
    items: [
      { productId: "PRD003", name: "芒果冰沙", quantity: 2, price: 28 },
    ],
  },
  {
    orderId: "ORD005", customerId: "C004", storeId: "S002", status: "completed", channel: "app",
    total: 150, discount: 5, paymentMethod: "alipay",
    createdAt: new Date("2026-03-25T11:20:00Z"),
    items: [
      { productId: "PRD004", name: "抹茶拿铁", quantity: 3, price: 30 },
      { productId: "PRD001", name: "拿铁咖啡", quantity: 2, price: 32 },
    ],
  },
  {
    orderId: "ORD006", customerId: "C002", storeId: "S005", status: "cancelled", channel: "online",
    total: 48, discount: 0, paymentMethod: "wechat",
    createdAt: new Date("2026-03-25T08:00:00Z"),
    items: [
      { productId: "PRD002", name: "美式咖啡", quantity: 2, price: 24 },
    ],
  },
  {
    orderId: "ORD007", customerId: "C005", storeId: "S004", status: "completed", channel: "store",
    total: 90, discount: 0, paymentMethod: "cash",
    createdAt: new Date("2026-03-26T13:30:00Z"),
    items: [
      { productId: "PRD004", name: "抹茶拿铁", quantity: 3, price: 30 },
    ],
  },
  {
    orderId: "ORD008", customerId: "C003", storeId: "S003", status: "pending", channel: "online",
    total: 36, discount: 0, paymentMethod: "wechat",
    createdAt: new Date("2026-03-26T17:00:00Z"),
    items: [
      { productId: "PRD005", name: "椰子水", quantity: 2, price: 18 },
    ],
  },
  {
    orderId: "ORD009", customerId: "C001", storeId: "S002", status: "completed", channel: "app",
    total: 280, discount: 30, paymentMethod: "alipay",
    createdAt: new Date("2026-03-27T10:00:00Z"),
    items: [
      { productId: "PRD001", name: "拿铁咖啡", quantity: 6, price: 32 },
      { productId: "PRD003", name: "芒果冰沙", quantity: 3, price: 28 },
    ],
  },
  {
    orderId: "ORD010", customerId: "C004", storeId: "S005", status: "completed", channel: "online",
    total: 72, discount: 0, paymentMethod: "wechat",
    createdAt: new Date("2026-03-28T15:30:00Z"),
    items: [
      { productId: "PRD002", name: "美式咖啡", quantity: 3, price: 24 },
    ],
  },
  {
    orderId: "ORD011", customerId: "C001", storeId: "S003", status: "completed", channel: "store",
    total: 35, discount: 0, paymentMethod: "cash",
    createdAt: new Date("2026-03-28T09:00:00Z"),
    items: [
      { productId: "PRD006", name: "燕麦拿铁", quantity: 1, price: 35 },
    ],
  },
  {
    orderId: "ORD012", customerId: "C005", storeId: "S004", status: "completed", channel: "app",
    total: 160, discount: 15, paymentMethod: "alipay",
    createdAt: new Date("2026-03-29T12:00:00Z"),
    items: [
      { productId: "PRD006", name: "燕麦拿铁", quantity: 2, price: 35 },
      { productId: "PRD004", name: "抹茶拿铁", quantity: 3, price: 30 },
    ],
  },
];

// completed: ORD001(120)+ORD002(88)+ORD003(210)+ORD005(150)+ORD007(90)+ORD009(280)+ORD010(72)+ORD011(35)+ORD012(160) = 9
// pending: ORD004+ORD008 = 2, cancelled: ORD006 = 1
const COMPLETED_COUNT = 9;
const TOTAL_ORDERS = 12;

describe("MongoDB Executor", () => {
  beforeAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);

    const container = await docker.createContainer({
      Image: "mongo:7",
      name: CONTAINER_NAME,
      HostConfig: {
        PortBindings: { "27017/tcp": [{ HostPort: String(MONGO_PORT) }] },
      },
    });
    await container.start();

    await waitForMongo(MONGO_URI, 30_000);

    const client = new MongoClient(MONGO_URI);
    await client.connect();
    const mdb = client.db(TEST_DB);
    await mdb.collection("customers").insertMany(CUSTOMERS);
    await mdb.collection("products").insertMany(PRODUCTS);
    await mdb.collection("orders").insertMany(ORDERS);
    await mdb.collection("stores").insertMany(STORES);
    await client.close();
  }, 60_000);

  afterAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);
  });

  // ── findDocuments — 基础 ──────────────────────────────

  describe("findDocuments — 基础", () => {
    it("简单 filter: status = completed", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: { status: "completed" },
      })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(COMPLETED_COUNT);
    });

    it("比较运算符: total > 100", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: { total: { $gt: 100 } },
      })) as Array<Record<string, unknown>>;
      for (const row of rows) expect(row.total as number).toBeGreaterThan(100);
    });

    it("$in 运算符", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: { channel: { $in: ["online", "app"] } },
      })) as Array<Record<string, unknown>>;
      for (const row of rows) expect(["online", "app"]).toContain(row.channel);
    });

    it("嵌套字段查询: items.name = 拿铁咖啡", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: { "items.name": "拿铁咖啡" },
      })) as Array<Record<string, unknown>>;
      expect(rows.length).toBeGreaterThanOrEqual(4);
    });

    it("sort + limit: 按 total 降序取前 3", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: {}, sort: { total: -1 }, limit: 3,
      })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(3);
      expect(rows[0].total).toBe(280);
    });

    it("空 filter 返回全部", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: {},
      })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(TOTAL_ORDERS);
    });
  });

  // ── findDocuments — 复杂查询 ─────────────────────────

  describe("findDocuments — 复杂查询", () => {
    it("$and + $or 组合: (online 或 app) 且 total >= 100", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders",
        filter: {
          $and: [
            { $or: [{ channel: "online" }, { channel: "app" }] },
            { total: { $gte: 100 } },
          ],
        },
      })) as Array<Record<string, unknown>>;
      for (const r of rows) {
        expect(["online", "app"]).toContain(r.channel);
        expect(r.total as number).toBeGreaterThanOrEqual(100);
      }
    });

    it("$regex: 模糊搜索客户名字包含 '三' 或 '四'", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "customers",
        filter: { name: { $regex: "三|四" } },
      })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(2); // 张三、李四
    });

    it("$elemMatch: items 中有 quantity>3 且 price>=30 的商品", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders",
        filter: { items: { $elemMatch: { quantity: { $gt: 3 }, price: { $gte: 30 } } } },
      })) as Array<Record<string, unknown>>;
      // ORD003 拿铁qty=5/price=32, ORD009 拿铁qty=6/price=32
      expect(rows).toHaveLength(2);
    });

    it("$expr: total 大于 items 数量 * 40 的订单", async () => {
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders",
        filter: { $expr: { $gt: ["$total", { $multiply: [{ $size: "$items" }, 40] }] } },
      })) as Array<Record<string, unknown>>;
      for (const r of rows) {
        const items = r.items as Array<unknown>;
        expect(r.total as number).toBeGreaterThan(items.length * 40);
      }
    });
  });

  // ── aggregate — 基础 ────────────────────────────────

  describe("aggregate — 基础", () => {
    it("$group: 按状态汇总金额", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $group: { _id: "$status", totalAmount: { $sum: "$total" }, count: { $sum: 1 } } },
          { $sort: { totalAmount: -1 } },
        ],
      })) as Array<{ _id: string; totalAmount: number; count: number }>;
      const completed = rows.find((r) => r._id === "completed");
      expect(completed!.count).toBe(COMPLETED_COUNT);
    });

    it("$unwind + $group: 按商品统计销量", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $unwind: "$items" },
          { $group: { _id: "$items.productId", totalQty: { $sum: "$items.quantity" } } },
          { $sort: { totalQty: -1 } },
        ],
      })) as Array<{ _id: string; totalQty: number }>;
      const latte = rows.find((r) => r._id === "PRD001");
      expect(latte!.totalQty).toBe(15); // 2+5+2+6=15
    });

    it("$lookup: orders → customers", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $match: { orderId: "ORD001" } },
          { $lookup: { from: "customers", localField: "customerId", foreignField: "customerId", as: "customer" } },
          { $unwind: "$customer" },
        ],
      })) as Array<{ customer: { name: string } }>;
      expect(rows).toHaveLength(1);
      expect(rows[0].customer.name).toBe("张三");
    });

    it("$sort + $limit: 金额 Top 3", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $sort: { total: -1 } },
          { $limit: 3 },
          { $project: { orderId: 1, total: 1, _id: 0 } },
        ],
      })) as Array<{ orderId: string; total: number }>;
      expect(rows).toHaveLength(3);
      expect(rows[0].total).toBe(280);
    });
  });

  // ── aggregate — 高级操作 ───────────────────────────

  describe("aggregate — 高级操作", () => {
    it("$facet: 并行计算多个维度", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [{
          $facet: {
            statusSummary: [
              { $group: { _id: "$status", count: { $sum: 1 }, total: { $sum: "$total" } } },
            ],
            channelSummary: [
              { $group: { _id: "$channel", count: { $sum: 1 } } },
            ],
            topOrders: [
              { $sort: { total: -1 } },
              { $limit: 3 },
              { $project: { orderId: 1, total: 1, _id: 0 } },
            ],
          },
        }],
      })) as Array<{
        statusSummary: Array<{ _id: string; count: number }>;
        channelSummary: Array<{ _id: string; count: number }>;
        topOrders: Array<{ orderId: string }>;
      }>;
      expect(rows).toHaveLength(1);
      expect(rows[0].statusSummary.length).toBe(3); // completed, pending, cancelled
      expect(rows[0].channelSummary.length).toBe(3); // online, app, store
      expect(rows[0].topOrders).toHaveLength(3);
    });

    it("$bucket: 按金额区间分桶", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [{
          $bucket: {
            groupBy: "$total",
            boundaries: [0, 50, 100, 200, 500],
            default: "500+",
            output: { count: { $sum: 1 }, orders: { $push: "$orderId" } },
          },
        }],
      })) as Array<{ _id: number | string; count: number; orders: string[] }>;
      const totalCount = rows.reduce((s, r) => s + r.count, 0);
      expect(totalCount).toBe(TOTAL_ORDERS);
      // 280 应该在 200-500 桶
      const bucket200 = rows.find((r) => r._id === 200);
      expect(bucket200).toBeDefined();
      expect(bucket200!.orders).toContain("ORD009");
    });

    it("多层 $lookup 链: orders → customers → 再看 store", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $match: { orderId: "ORD001" } },
          { $lookup: { from: "customers", localField: "customerId", foreignField: "customerId", as: "customer" } },
          { $unwind: "$customer" },
          { $lookup: { from: "stores", localField: "storeId", foreignField: "storeId", as: "store" } },
          { $unwind: "$store" },
          { $project: { orderId: 1, "customer.name": 1, "store.name": 1, "store.city": 1, total: 1, _id: 0 } },
        ],
      })) as Array<{ orderId: string; customer: { name: string }; store: { name: string; city: string } }>;
      expect(rows).toHaveLength(1);
      expect(rows[0].customer.name).toBe("张三");
      expect(rows[0].store.name).toBe("南京西路店");
      expect(rows[0].store.city).toBe("上海");
    });

    it("$addFields + $project: 计算 itemCount、avgItemPrice", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $addFields: {
            itemCount: { $size: "$items" },
            computedTotal: { $reduce: {
              input: "$items",
              initialValue: 0,
              in: { $add: ["$$value", { $multiply: ["$$this.quantity", "$$this.price"] }] },
            }},
          }},
          { $addFields: {
            avgItemPrice: { $cond: [
              { $gt: ["$itemCount", 0] },
              { $round: [{ $divide: ["$computedTotal", { $sum: { $map: { input: "$items", as: "i", in: "$$i.quantity" } } }] }, 2] },
              0,
            ]},
          }},
          { $project: { orderId: 1, itemCount: 1, computedTotal: 1, avgItemPrice: 1, _id: 0 } },
          { $sort: { computedTotal: -1 } },
        ],
      })) as Array<{ orderId: string; itemCount: number; computedTotal: number; avgItemPrice: number }>;
      expect(rows.length).toBe(TOTAL_ORDERS);
      // ORD009: items=[{qty:6,price:32},{qty:3,price:28}] → computedTotal=6*32+3*28=276
      const ord9 = rows.find((r) => r.orderId === "ORD009");
      expect(ord9!.computedTotal).toBe(276);
      expect(ord9!.itemCount).toBe(2);
    });

    it("$cond / $switch: 条件分组", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $addFields: {
            tier: { $switch: {
              branches: [
                { case: { $gte: ["$total", 200] }, then: "高客单" },
                { case: { $gte: ["$total", 100] }, then: "中客单" },
              ],
              default: "低客单",
            }},
          }},
          { $group: { _id: "$tier", count: { $sum: 1 }, avgTotal: { $avg: "$total" } } },
          { $sort: { avgTotal: -1 } },
        ],
      })) as Array<{ _id: string; count: number; avgTotal: number }>;
      const totalCount = rows.reduce((s, r) => s + r.count, 0);
      expect(totalCount).toBe(TOTAL_ORDERS);
      const high = rows.find((r) => r._id === "高客单");
      expect(high).toBeDefined();
      expect(high!.avgTotal).toBeGreaterThanOrEqual(200);
    });

    it("日期聚合: 按 dayOfWeek 统计", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $addFields: {
            dayOfWeek: { $dayOfWeek: "$createdAt" },
            yearMonth: { $dateToString: { format: "%Y-%m", date: "$createdAt" } },
          }},
          { $group: {
            _id: "$dayOfWeek",
            count: { $sum: 1 },
            totalRevenue: { $sum: "$total" },
          }},
          { $sort: { _id: 1 } },
        ],
      })) as Array<{ _id: number; count: number; totalRevenue: number }>;
      expect(rows.length).toBeGreaterThan(0);
      // dayOfWeek 值在 1-7 之间
      for (const r of rows) {
        expect(r._id).toBeGreaterThanOrEqual(1);
        expect(r._id).toBeLessThanOrEqual(7);
      }
    });

    it("$filter + $map: 过滤高价商品并计算小计", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $project: {
            orderId: 1,
            _id: 0,
            premiumItems: {
              $filter: { input: "$items", as: "item", cond: { $gte: ["$$item.price", 28] } },
            },
          }},
          { $addFields: {
            premiumSubtotals: {
              $map: {
                input: "$premiumItems",
                as: "item",
                in: { name: "$$item.name", subtotal: { $multiply: ["$$item.quantity", "$$item.price"] } },
              },
            },
          }},
          { $match: { "premiumItems.0": { $exists: true } } }, // 有高价商品的订单
        ],
      })) as Array<{ orderId: string; premiumSubtotals: Array<{ name: string; subtotal: number }> }>;
      expect(rows.length).toBeGreaterThan(0);
      for (const r of rows) {
        for (const item of r.premiumSubtotals) {
          expect(item.subtotal).toBeGreaterThan(0);
        }
      }
    });

    it("$reduce: 手动计算 items 总价", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $addFields: {
            computedTotal: {
              $reduce: {
                input: "$items",
                initialValue: 0,
                in: { $add: ["$$value", { $multiply: ["$$this.quantity", "$$this.price"] }] },
              },
            },
          }},
          { $project: { orderId: 1, total: 1, computedTotal: 1, _id: 0 } },
        ],
      })) as Array<{ orderId: string; total: number; computedTotal: number }>;
      // ORD001: 2*32+2*28=120, total=120
      const ord1 = rows.find((r) => r.orderId === "ORD001");
      expect(ord1!.computedTotal).toBe(120);
    });

    it("$group + $push + $addToSet: 按客户收集订单和渠道", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $group: {
            _id: "$customerId",
            orderIds: { $push: "$orderId" },
            channels: { $addToSet: "$channel" },
            totalSpent: { $sum: "$total" },
            orderCount: { $sum: 1 },
          }},
          { $sort: { totalSpent: -1 } },
        ],
      })) as Array<{
        _id: string; orderIds: string[]; channels: string[];
        totalSpent: number; orderCount: number;
      }>;
      // C001 有 ORD001,ORD003,ORD009,ORD011 → 4 单
      const c001 = rows.find((r) => r._id === "C001");
      expect(c001!.orderCount).toBe(4);
      expect(c001!.orderIds).toContain("ORD001");
      expect(c001!.orderIds).toContain("ORD009");
      // channels 用 $addToSet 去重
      expect(new Set(c001!.channels).size).toBe(c001!.channels.length);
    });

    it("$replaceRoot: 展平嵌套 items 为行级视图", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $match: { orderId: "ORD002" } },
          { $unwind: "$items" },
          { $replaceRoot: {
            newRoot: { $mergeObjects: [
              "$items",
              { orderId: "$orderId", orderTotal: "$total" },
            ]},
          }},
        ],
      })) as Array<{ orderId: string; productId: string; name: string; quantity: number }>;
      // ORD002 有 3 个 item
      expect(rows).toHaveLength(3);
      for (const r of rows) {
        expect(r.orderId).toBe("ORD002");
        expect(r.productId).toBeDefined();
        expect(r.name).toBeDefined();
      }
    });

    it("嵌套 $group: 先按 customer+product 分组，再取每个产品的 top customer", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $unwind: "$items" },
          // 第一层: 按 customer + product 分组
          { $group: {
            _id: { customerId: "$customerId", productId: "$items.productId" },
            totalQty: { $sum: "$items.quantity" },
          }},
          // 第二层: 按 product 排序取 top customer
          { $sort: { "_id.productId": 1, totalQty: -1 } },
          { $group: {
            _id: "$_id.productId",
            topCustomer: { $first: "$_id.customerId" },
            topQty: { $first: "$totalQty" },
          }},
          { $sort: { topQty: -1 } },
        ],
      })) as Array<{ _id: string; topCustomer: string; topQty: number }>;
      // PRD001 (拿铁) top customer 应该是 C001 (ORD001:2 + ORD003:5 + ORD009:6 = 13)
      const latte = rows.find((r) => r._id === "PRD001");
      expect(latte!.topCustomer).toBe("C001");
      expect(latte!.topQty).toBe(13);
    });

    it("$graphLookup: 门店层级递归查询", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "stores",
        pipeline: [
          { $match: { storeId: "S001" } }, // 从华东总部开始
          { $graphLookup: {
            from: "stores",
            startWith: "$storeId",
            connectFromField: "storeId",
            connectToField: "parentStoreId",
            as: "subsidiaries",
            maxDepth: 5,
          }},
          { $project: { storeId: 1, name: 1, subsidiaryCount: { $size: "$subsidiaries" }, subsidiaries: "$subsidiaries.name", _id: 0 } },
        ],
      })) as Array<{ storeId: string; name: string; subsidiaryCount: number; subsidiaries: string[] }>;
      expect(rows).toHaveLength(1);
      expect(rows[0].name).toBe("华东总部");
      // S001 下有 S002(南京西路) 和 S003(杭州银泰)
      expect(rows[0].subsidiaryCount).toBe(2);
      expect(rows[0].subsidiaries).toContain("南京西路店");
      expect(rows[0].subsidiaries).toContain("杭州银泰店");
    });

    it("$unionWith: 合并 orders 和 products 为统一视图", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $project: { type: { $literal: "order" }, id: "$orderId", name: { $literal: "order" }, value: "$total", _id: 0 } },
          { $unionWith: {
            coll: "products",
            pipeline: [
              { $project: { type: { $literal: "product" }, id: "$productId", name: "$name", value: "$price", _id: 0 } },
            ],
          }},
          { $sort: { type: 1, value: -1 } },
        ],
      })) as Array<{ type: string; id: string; value: number }>;
      const orderRows = rows.filter((r) => r.type === "order");
      const productRows = rows.filter((r) => r.type === "product");
      expect(orderRows.length).toBe(TOTAL_ORDERS);
      expect(productRows.length).toBe(6);
    });
  });

  // ── aggregate — 超复杂组合 ─────────────────────────

  describe("aggregate — 超复杂组合", () => {
    it("match → unwind → lookup products → group by category → sort → facet", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          // 1. 只看 completed 订单
          { $match: { status: "completed" } },
          // 2. 展开商品
          { $unwind: "$items" },
          // 3. 关联 products 获取 category 和 cost
          { $lookup: { from: "products", localField: "items.productId", foreignField: "productId", as: "product" } },
          { $unwind: "$product" },
          // 4. 计算每行利润
          { $addFields: {
            lineRevenue: { $multiply: ["$items.quantity", "$items.price"] },
            lineCost: { $multiply: ["$items.quantity", "$product.cost"] },
          }},
          { $addFields: {
            lineProfit: { $subtract: ["$lineRevenue", "$lineCost"] },
          }},
          // 5. 并行分析
          { $facet: {
            // 按产品类别汇总
            byCategory: [
              { $group: {
                _id: "$product.category",
                totalRevenue: { $sum: "$lineRevenue" },
                totalProfit: { $sum: "$lineProfit" },
                totalQty: { $sum: "$items.quantity" },
              }},
              { $addFields: { profitMargin: { $round: [{ $multiply: [{ $divide: ["$totalProfit", "$totalRevenue"] }, 100] }, 2] } } },
              { $sort: { totalRevenue: -1 } },
            ],
            // 按客户汇总
            byCustomer: [
              { $group: {
                _id: "$customerId",
                totalRevenue: { $sum: "$lineRevenue" },
                uniqueProducts: { $addToSet: "$items.productId" },
              }},
              { $addFields: { productCount: { $size: "$uniqueProducts" } } },
              { $sort: { totalRevenue: -1 } },
              { $limit: 3 },
            ],
            // 总计
            grandTotal: [
              { $group: {
                _id: null,
                totalRevenue: { $sum: "$lineRevenue" },
                totalProfit: { $sum: "$lineProfit" },
                totalOrders: { $addToSet: "$orderId" },
              }},
              { $addFields: { orderCount: { $size: "$totalOrders" } } },
            ],
          }},
        ],
      })) as Array<{
        byCategory: Array<{ _id: string; totalRevenue: number; profitMargin: number }>;
        byCustomer: Array<{ _id: string; totalRevenue: number; productCount: number }>;
        grandTotal: Array<{ totalRevenue: number; orderCount: number }>;
      }>;
      expect(rows).toHaveLength(1);
      const result = rows[0];
      // 3 个类别
      expect(result.byCategory.length).toBe(3);
      for (const cat of result.byCategory) {
        expect(cat.profitMargin).toBeGreaterThan(0);
        expect(cat.profitMargin).toBeLessThan(100);
      }
      // top 3 客户
      expect(result.byCustomer.length).toBeLessThanOrEqual(3);
      // C001 应该排第一（消费最多）
      expect(result.byCustomer[0]._id).toBe("C001");
      // 总计
      expect(result.grandTotal[0].orderCount).toBe(COMPLETED_COUNT);
    });

    it("多阶段: 门店维度 → lookup → 日期分析 → 排名", async () => {
      const rows = (await mongoExecutor(connInfo, "aggregate", {
        database: TEST_DB, collection: "orders",
        pipeline: [
          { $match: { status: "completed" } },
          // 关联门店
          { $lookup: { from: "stores", localField: "storeId", foreignField: "storeId", as: "store" } },
          { $unwind: "$store" },
          // 按门店+日期聚合
          { $group: {
            _id: {
              storeId: "$storeId",
              storeName: "$store.name",
              region: "$store.region",
              date: { $dateToString: { format: "%Y-%m-%d", date: "$createdAt" } },
            },
            dailyRevenue: { $sum: "$total" },
            orderCount: { $sum: 1 },
          }},
          // 按门店聚合日均
          { $group: {
            _id: { storeId: "$_id.storeId", storeName: "$_id.storeName", region: "$_id.region" },
            totalRevenue: { $sum: "$dailyRevenue" },
            activeDays: { $sum: 1 },
            avgDailyRevenue: { $avg: "$dailyRevenue" },
            peakDayRevenue: { $max: "$dailyRevenue" },
          }},
          // 排名
          { $sort: { totalRevenue: -1 } },
          { $group: {
            _id: null,
            stores: { $push: {
              name: "$_id.storeName",
              region: "$_id.region",
              totalRevenue: "$totalRevenue",
              activeDays: "$activeDays",
              avgDailyRevenue: { $round: ["$avgDailyRevenue", 2] },
              peakDayRevenue: "$peakDayRevenue",
            }},
            grandTotal: { $sum: "$totalRevenue" },
          }},
          // 添加占比
          { $unwind: { path: "$stores", includeArrayIndex: "rank" } },
          { $addFields: {
            "stores.rank": { $add: ["$rank", 1] },
            "stores.pctOfTotal": { $round: [{ $multiply: [{ $divide: ["$stores.totalRevenue", "$grandTotal"] }, 100] }, 2] },
          }},
          { $replaceRoot: { newRoot: "$stores" } },
        ],
      })) as Array<{
        name: string; region: string; totalRevenue: number;
        rank: number; pctOfTotal: number;
      }>;
      expect(rows.length).toBeGreaterThan(0);
      expect(rows[0].rank).toBe(1);
      const totalPct = rows.reduce((s, r) => s + r.pctOfTotal, 0);
      expect(totalPct).toBeCloseTo(100, 0);
    });
  });

  // ── countDocuments ───────────────────────────────────

  describe("countDocuments", () => {
    it("带 filter 计数", async () => {
      const count = await mongoExecutor(connInfo, "countDocuments", {
        database: TEST_DB, collection: "orders", filter: { status: "completed" },
      });
      expect(count).toBe(COMPLETED_COUNT);
    });

    it("空 filter 总数", async () => {
      const count = await mongoExecutor(connInfo, "countDocuments", {
        database: TEST_DB, collection: "orders", filter: {},
      });
      expect(count).toBe(TOTAL_ORDERS);
    });
  });

  // ── 元数据 ──────────────────────────────────────────

  describe("元数据", () => {
    it("listCollections 包含所有集合", async () => {
      const cols = (await mongoExecutor(connInfo, "listCollections", { database: TEST_DB })) as Array<{ name: string }>;
      const names = cols.map((c) => c.name);
      expect(names).toContain("orders");
      expect(names).toContain("customers");
      expect(names).toContain("products");
      expect(names).toContain("stores");
    });

    it("listDatabases 包含 testdb", async () => {
      const dbs = (await mongoExecutor(connInfo, "listDatabases", {})) as Array<{ name: string }>;
      expect(dbs.map((d) => d.name)).toContain(TEST_DB);
    });
  });

  // ── 写操作 ──────────────────────────────────────────

  describe("写操作", () => {
    it("insertOne + 验证", async () => {
      await mongoExecutor(connInfo, "insertOne", {
        database: TEST_DB, collection: "orders",
        document: {
          orderId: "ORD_NEW_1", customerId: "C001", storeId: "S002", status: "completed",
          channel: "app", total: 999, discount: 0, paymentMethod: "wechat",
          items: [{ productId: "PRD001", name: "拿铁咖啡", quantity: 10, price: 32 }],
          createdAt: new Date("2026-04-01"),
        },
      });
      const rows = (await mongoExecutor(connInfo, "findDocuments", {
        database: TEST_DB, collection: "orders", filter: { orderId: "ORD_NEW_1" },
      })) as Array<Record<string, unknown>>;
      expect(rows).toHaveLength(1);
      expect(rows[0].total).toBe(999);
    });

    it("updateMany + 验证", async () => {
      const result = (await mongoExecutor(connInfo, "updateMany", {
        database: TEST_DB, collection: "orders",
        filter: { status: "pending" }, update: { $set: { status: "shipped" } },
      })) as { modifiedCount: number };
      expect(result.modifiedCount).toBe(2);
      const count = await mongoExecutor(connInfo, "countDocuments", {
        database: TEST_DB, collection: "orders", filter: { status: "shipped" },
      });
      expect(count).toBe(2);
    });

    it("deleteMany + 验证", async () => {
      const beforeCount = (await mongoExecutor(connInfo, "countDocuments", {
        database: TEST_DB, collection: "orders", filter: {},
      })) as number;
      const result = (await mongoExecutor(connInfo, "deleteMany", {
        database: TEST_DB, collection: "orders", filter: { status: "cancelled" },
      })) as { deletedCount: number };
      expect(result.deletedCount).toBe(1);
      const afterCount = (await mongoExecutor(connInfo, "countDocuments", {
        database: TEST_DB, collection: "orders", filter: {},
      })) as number;
      expect(afterCount).toBe(beforeCount - 1);
    });
  });

  // ── executeService 端到端 ──────────────────────────

  describe("executeService 端到端", () => {
    it("注册 MongoDB service + aggregate", async () => {
      const serviceId = await insertServiceRecord({
        name: "test-mongo-exec",
        serviceType: "mongodb",
        host: "127.0.0.1",
        port: MONGO_PORT,
      });
      const rows = (await executeService(serviceId, "aggregate", {
        database: TEST_DB, collection: "customers",
        pipeline: [
          { $group: { _id: "$tier", count: { $sum: 1 } } },
          { $sort: { count: -1 } },
        ],
      })) as Array<{ _id: string; count: number }>;
      expect(rows.length).toBeGreaterThan(0);
    });
  });

  // ── 错误处理 ──────────────────────────────────────────

  describe("错误处理", () => {
    it("缺少 collection 参数报错", async () => {
      await expect(
        mongoExecutor(connInfo, "findDocuments", { database: TEST_DB }),
      ).rejects.toThrow("参数 collection 不能为空");
    });

    it("不支持的 operation 报错", async () => {
      await expect(mongoExecutor(connInfo, "unknownOp", {})).rejects.toThrow(
        'unsupported operation "unknownOp"',
      );
    });
  });
});
