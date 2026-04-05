import { db } from "@/db/connection";
import { servers } from "@/db/schema";
import { count, desc, eq } from "drizzle-orm";
import { cryptoService } from "@/lib/crypto";
import { NotFoundError, ValidationError } from "@/lib/errors";
import { Client } from "ssh2";

interface ServerCreateInput {
  name: string;
  description?: string | null;
  host: string;
  port?: number;
  username?: string;
  password?: string | null;
  privateKey?: string | null;
  bastionHost?: string | null;
  bastionPort?: number | null;
  bastionUsername?: string | null;
  bastionPassword?: string | null;
  bastionPrivateKey?: string | null;
  sudoPassword?: string | null;
  useSshPasswordForSudo?: boolean;
}

interface ServerUpdateInput {
  name?: string;
  description?: string | null;
  host?: string;
  port?: number;
  username?: string;
  password?: string | null;
  privateKey?: string | null;
  bastionHost?: string | null;
  bastionPort?: number | null;
  bastionUsername?: string | null;
  bastionPassword?: string | null;
  bastionPrivateKey?: string | null;
  sudoPassword?: string | null;
  useSshPasswordForSudo?: boolean;
}

async function encryptOptional(value: string | null | undefined) {
  if (!value) return value === null ? null : undefined;
  return cryptoService.encrypt(value);
}

export async function create(input: ServerCreateInput) {
  if (!input.host) {
    throw new ValidationError("SSH server requires host");
  }

  const [duplicate] = await db.select().from(servers).where(eq(servers.name, input.name));
  if (duplicate) {
    throw new ValidationError("Server name already exists");
  }

  const [server] = await db
    .insert(servers)
    .values({
      name: input.name,
      description: input.description,
      host: input.host,
      port: input.port ?? 22,
      username: input.username ?? "root",
      encryptedPassword: await encryptOptional(input.password),
      encryptedPrivateKey: await encryptOptional(input.privateKey),
      bastionHost: input.bastionHost,
      bastionPort: input.bastionPort,
      bastionUsername: input.bastionUsername,
      encryptedBastionPassword: await encryptOptional(input.bastionPassword),
      encryptedBastionPrivateKey: await encryptOptional(input.bastionPrivateKey),
      encryptedSudoPassword: await encryptOptional(input.sudoPassword),
      useSshPasswordForSudo: input.useSshPasswordForSudo ?? true,
    })
    .returning();
  return server;
}

export async function get(id: string) {
  const [server] = await db.select().from(servers).where(eq(servers.id, id));
  if (!server) throw new NotFoundError("Server not found");
  return server;
}

export async function list(page: number, pageSize: number) {
  const [items, [{ value: total }]] = await Promise.all([
    db.select().from(servers).orderBy(desc(servers.createdAt)).offset((page - 1) * pageSize).limit(pageSize),
    db.select({ value: count() }).from(servers),
  ]);
  return { items, total, page, pageSize };
}

export async function update(id: string, input: ServerUpdateInput) {
  const [existing] = await db.select().from(servers).where(eq(servers.id, id));
  if (!existing) throw new NotFoundError("Server not found");

  if (input.name && input.name !== existing.name) {
    const [dup] = await db.select().from(servers).where(eq(servers.name, input.name));
    if (dup) throw new ValidationError("Server name already exists");
  }

  const set: Record<string, unknown> = {};

  // Plain fields
  for (const field of ["name", "description", "host", "port", "username", "bastionHost", "bastionPort", "bastionUsername", "useSshPasswordForSudo"] as const) {
    if (input[field] !== undefined) set[field] = input[field];
  }

  // Encrypted fields
  if (input.password !== undefined) set.encryptedPassword = await encryptOptional(input.password);
  if (input.privateKey !== undefined) set.encryptedPrivateKey = await encryptOptional(input.privateKey);
  if (input.bastionPassword !== undefined) set.encryptedBastionPassword = await encryptOptional(input.bastionPassword);
  if (input.bastionPrivateKey !== undefined) set.encryptedBastionPrivateKey = await encryptOptional(input.bastionPrivateKey);
  if (input.sudoPassword !== undefined) set.encryptedSudoPassword = await encryptOptional(input.sudoPassword);

  const [updated] = await db.update(servers).set(set).where(eq(servers.id, id)).returning();
  return updated;
}

export async function remove(id: string) {
  const [existing] = await db.select().from(servers).where(eq(servers.id, id));
  if (!existing) throw new NotFoundError("Server not found");
  await db.delete(servers).where(eq(servers.id, id));
}

export async function testSSH(params: {
  host: string;
  port?: number;
  username?: string;
  password?: string | null;
  privateKey?: string | null;
}): Promise<{ success: boolean; message: string }> {
  return new Promise((resolve) => {
    const conn = new Client();
    const timeout = setTimeout(() => {
      conn.end();
      resolve({ success: false, message: "SSH 连接超时" });
    }, 10_000);

    conn.on("ready", () => {
      clearTimeout(timeout);
      conn.end();
      resolve({ success: true, message: "SSH 连接测试成功" });
    });

    conn.on("error", (err) => {
      clearTimeout(timeout);
      resolve({ success: false, message: `SSH 连接失败: ${err.message}` });
    });

    const config: Record<string, unknown> = {
      host: params.host,
      port: params.port ?? 22,
      username: params.username ?? "root",
      readyTimeout: 10_000,
    };

    if (params.privateKey) {
      config.privateKey = params.privateKey;
    } else if (params.password) {
      config.password = params.password;
    }

    conn.connect(config);
  });
}

export async function testSavedServer(id: string) {
  const server = await get(id);
  const password = server.encryptedPassword ? await cryptoService.decrypt(server.encryptedPassword) : null;
  const privateKey = server.encryptedPrivateKey ? await cryptoService.decrypt(server.encryptedPrivateKey) : null;

  const result = await testSSH({
    host: server.host,
    port: server.port,
    username: server.username,
    password,
    privateKey,
  });

  // Update status
  await db
    .update(servers)
    .set({ status: result.success ? "online" : "offline" })
    .where(eq(servers.id, id));

  return result;
}

export function toResponse(server: typeof servers.$inferSelect) {
  const authMethod = server.encryptedPrivateKey
    ? "private_key"
    : server.encryptedPassword
      ? "password"
      : "none";
  return {
    id: server.id,
    name: server.name,
    description: server.description,
    host: server.host,
    port: server.port,
    username: server.username,
    status: server.status,
    authMethod,
    hasBastion: !!server.bastionHost,
    bastionHost: server.bastionHost,
    useSshPasswordForSudo: server.useSshPasswordForSudo,
    createdAt: server.createdAt.toISOString(),
    updatedAt: server.updatedAt.toISOString(),
  };
}
