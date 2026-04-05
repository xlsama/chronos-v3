import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { join } from "path";
import { authMiddleware, getUser } from "@/lib/jwt";
import { uploadsDir } from "@/lib/paths";
import { NotFoundError, ValidationError } from "@/lib/errors";
import * as authService from "@/service/auth";

const registerSchema = z.object({
  email: z.email(),
  password: z.string().min(6),
  name: z.string().min(1).max(255),
});

const loginSchema = z.object({
  email: z.email(),
  password: z.string(),
});

const changePasswordSchema = z.object({
  oldPassword: z.string(),
  newPassword: z.string().min(6),
});

function userResponse(user: {
  id: string;
  email: string;
  name: string;
  avatar: string | null;
  isActive: boolean;
  createdAt: Date;
}) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    avatar: user.avatar,
    isActive: user.isActive,
    createdAt: user.createdAt.toISOString(),
  };
}

const app = new Hono();

// ── Public routes ───────────────────────────────────────────

app.post("/register", zValidator("json", registerSchema), async (c) => {
  const { email, password, name } = c.req.valid("json");
  const user = await authService.register(email, password, name);
  return c.json(userResponse(user), 201);
});

app.post("/login", zValidator("json", loginSchema), async (c) => {
  const { email, password } = c.req.valid("json");
  const user = await authService.authenticate(email, password);
  const accessToken = await authService.generateToken(user.id, user.email);
  return c.json({ accessToken, tokenType: "bearer" });
});

app.get("/avatar/:filename", async (c) => {
  const filename = c.req.param("filename");
  const filePath = join(uploadsDir(), filename);
  const file = Bun.file(filePath);
  if (!(await file.exists())) {
    throw new NotFoundError("头像不存在");
  }
  return new Response(file, {
    headers: { "Content-Type": file.type },
  });
});

// ── Protected routes ────────────────────────────────────────

app.get("/me", authMiddleware, async (c) => {
  return c.json(userResponse(getUser(c)));
});

app.put("/avatar", authMiddleware, async (c) => {
  const formData = await c.req.formData();
  const file = formData.get("file");
  if (!(file instanceof File)) {
    throw new ValidationError("缺少文件");
  }

  const ext = file.name.split(".").pop()?.toLowerCase();
  if (!ext || !["png", "jpg", "jpeg", "webp"].includes(ext)) {
    throw new ValidationError("仅支持 png/jpg/jpeg/webp 格式");
  }

  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > 5 * 1024 * 1024) {
    throw new ValidationError("头像文件不能超过 5MB");
  }

  const user = getUser(c);

  // Delete old avatar
  if (user.avatar) {
    const oldFile = Bun.file(join(uploadsDir(), user.avatar));
    if (await oldFile.exists()) {
      const { unlink } = await import("fs/promises");
      await unlink(join(uploadsDir(), user.avatar));
    }
  }

  // Save new file
  const storedName = `${crypto.randomUUID()}.${ext}`;
  const dir = uploadsDir();
  await Bun.write(join(dir, storedName), bytes);

  // Update user
  const { db } = await import("@/db/connection");
  const { users } = await import("@/db/schema");
  const { eq } = await import("drizzle-orm");
  const [updated] = await db
    .update(users)
    .set({ avatar: storedName })
    .where(eq(users.id, user.id))
    .returning();

  return c.json(userResponse(updated));
});

app.put("/password", authMiddleware, zValidator("json", changePasswordSchema), async (c) => {
  const { oldPassword, newPassword } = c.req.valid("json");
  const user = getUser(c);
  const updated = await authService.changePassword(user.id, oldPassword, newPassword);
  return c.json(userResponse(updated));
});

export default app;
