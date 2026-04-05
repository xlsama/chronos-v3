import { SignJWT, jwtVerify } from "jose";
import type { Context, Next } from "hono";
import { env } from "@/env";
import { db } from "@/db/connection";
import { users, type User } from "@/db/schema";
import { eq } from "drizzle-orm";
import { AuthenticationError } from "@/lib/errors";

const secret = new TextEncoder().encode(env.JWT_SECRET);

export async function createAccessToken(userId: string, email: string): Promise<string> {
  const jwt = new SignJWT({ sub: userId, email })
    .setProtectedHeader({ alg: "HS256" });

  if (env.JWT_EXPIRATION !== "0") {
    jwt.setExpirationTime(env.JWT_EXPIRATION);
  }

  return jwt.sign(secret);
}

export async function verifyTokenAndGetUser(authHeader: string | null | undefined): Promise<User> {
  if (!authHeader?.startsWith("Bearer ")) {
    throw new AuthenticationError("Missing authorization token");
  }

  const token = authHeader.slice(7);
  let payload: { sub?: string };
  try {
    const result = await jwtVerify(token, secret, { algorithms: ["HS256"] });
    payload = result.payload as { sub?: string };
  } catch (err: unknown) {
    const message = err instanceof Error && err.message.includes("expired")
      ? "Token expired"
      : "Invalid token";
    throw new AuthenticationError(message);
  }

  if (!payload.sub) {
    throw new AuthenticationError("Invalid token payload");
  }

  const [user] = await db.select().from(users).where(eq(users.id, payload.sub));
  if (!user || !user.isActive) {
    throw new AuthenticationError("User not found or deactivated");
  }

  return user;
}

export async function authMiddleware(c: Context, next: Next) {
  const user = await verifyTokenAndGetUser(c.req.header("Authorization"));
  c.set("user", user);
  await next();
}

// Type helper
export function getUser(c: Context): User {
  return c.get("user") as User;
}
