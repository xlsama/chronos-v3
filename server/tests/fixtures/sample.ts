import { Hono } from "hono";
import { z } from "zod";

const app = new Hono();

// 健康检查接口
app.get("/health", (c) => c.json({ status: "ok" }));

// 用户列表接口 - 支持分页
const querySchema = z.object({
  page: z.coerce.number().default(1),
  pageSize: z.coerce.number().default(20),
});

app.get("/api/users", async (c) => {
  const { page, pageSize } = querySchema.parse(c.req.query());
  const users = await db.select().from(usersTable).limit(pageSize).offset((page - 1) * pageSize);
  return c.json({ items: users, page, pageSize });
});

// 创建用户接口
const createUserSchema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
});

app.post("/api/users", async (c) => {
  const body = createUserSchema.parse(await c.req.json());
  const [user] = await db.insert(usersTable).values(body).returning();
  return c.json(user, 201);
});

export default app;
