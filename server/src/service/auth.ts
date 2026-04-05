import bcrypt from "bcrypt";
import { db } from "@/db/connection";
import { users } from "@/db/schema";
import { eq } from "drizzle-orm";
import { AuthenticationError, ConflictError } from "@/lib/errors";
import { createAccessToken } from "@/lib/jwt";

export async function register(email: string, password: string, name: string) {
  const [existing] = await db.select().from(users).where(eq(users.email, email));
  if (existing) {
    throw new ConflictError("该邮箱已注册");
  }

  const hashedPassword = await bcrypt.hash(password, 10);
  const [user] = await db
    .insert(users)
    .values({ email, hashedPassword, name })
    .returning();
  return user;
}

export async function authenticate(email: string, password: string) {
  const [user] = await db.select().from(users).where(eq(users.email, email));
  if (!user) {
    throw new AuthenticationError("该邮箱未注册");
  }
  if (!(await bcrypt.compare(password, user.hashedPassword))) {
    throw new AuthenticationError("密码错误");
  }
  if (!user.isActive) {
    throw new AuthenticationError("账号已停用");
  }
  return user;
}

export async function generateToken(userId: string, email: string) {
  return createAccessToken(userId, email);
}

export async function changePassword(userId: string, oldPassword: string, newPassword: string) {
  const [user] = await db.select().from(users).where(eq(users.id, userId));
  if (!user) {
    throw new AuthenticationError("用户不存在");
  }
  if (!(await bcrypt.compare(oldPassword, user.hashedPassword))) {
    throw new AuthenticationError("旧密码不正确");
  }

  const hashedPassword = await bcrypt.hash(newPassword, 10);
  const [updated] = await db
    .update(users)
    .set({ hashedPassword })
    .where(eq(users.id, userId))
    .returning();
  return updated;
}
