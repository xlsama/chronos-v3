import { db } from "@/db/connection";
import { services } from "@/db/schema";
import { count, desc, eq } from "drizzle-orm";
import { cryptoService } from "@/lib/crypto";
import { NotFoundError, ValidationError } from "@/lib/errors";

interface ServiceCreateInput {
  name: string;
  description?: string | null;
  serviceType: string;
  host: string;
  port: number;
  password?: string | null;
  config?: Record<string, unknown>;
}

interface ServiceUpdateInput {
  name?: string;
  description?: string | null;
  serviceType?: string;
  host?: string;
  port?: number;
  password?: string | null;
  config?: Record<string, unknown>;
}

export async function create(input: ServiceCreateInput) {
  const [duplicate] = await db.select().from(services).where(eq(services.name, input.name));
  if (duplicate) {
    throw new ValidationError("Service name already exists");
  }

  const [service] = await db
    .insert(services)
    .values({
      name: input.name,
      description: input.description,
      serviceType: input.serviceType,
      host: input.host,
      port: input.port,
      config: input.config ?? {},
      encryptedPassword: input.password ? await cryptoService.encrypt(input.password) : null,
    })
    .returning();
  return service;
}

export async function get(id: string) {
  const [service] = await db.select().from(services).where(eq(services.id, id));
  if (!service) throw new NotFoundError("Service not found");
  return service;
}

export async function list(page: number, pageSize: number, serviceType?: string) {
  let query = db.select().from(services);
  let countQuery = db.select({ value: count() }).from(services);

  if (serviceType) {
    query = query.where(eq(services.serviceType, serviceType)) as typeof query;
    countQuery = countQuery.where(eq(services.serviceType, serviceType)) as typeof countQuery;
  }

  const [items, [{ value: total }]] = await Promise.all([
    query.orderBy(desc(services.createdAt)).offset((page - 1) * pageSize).limit(pageSize),
    countQuery,
  ]);
  return { items, total, page, pageSize };
}

export async function update(id: string, input: ServiceUpdateInput) {
  const [existing] = await db.select().from(services).where(eq(services.id, id));
  if (!existing) throw new NotFoundError("Service not found");

  if (input.name && input.name !== existing.name) {
    const [dup] = await db.select().from(services).where(eq(services.name, input.name));
    if (dup) throw new ValidationError("Service name already exists");
  }

  const set: Record<string, unknown> = {};
  for (const field of ["name", "description", "serviceType", "host", "port", "config"] as const) {
    if (input[field] !== undefined) set[field] = input[field];
  }

  if (input.password !== undefined) {
    set.encryptedPassword = input.password ? await cryptoService.encrypt(input.password) : null;
  }

  const [updated] = await db.update(services).set(set).where(eq(services.id, id)).returning();
  return updated;
}

export async function remove(id: string) {
  const [existing] = await db.select().from(services).where(eq(services.id, id));
  if (!existing) throw new NotFoundError("Service not found");
  await db.delete(services).where(eq(services.id, id));
}

export async function testConnection(id: string): Promise<{ success: boolean; message: string }> {
  const service = await get(id);
  // Simplified connection test — just TCP probe for now
  try {
    const socket = await Bun.connect({
      hostname: service.host,
      port: service.port,
      socket: {
        data() {},
        open(socket) { socket.end(); },
        error() {},
      },
    });
    socket.end();
    await db.update(services).set({ status: "online" }).where(eq(services.id, id));
    return { success: true, message: "连接测试成功" };
  } catch {
    await db.update(services).set({ status: "offline" }).where(eq(services.id, id));
    return { success: false, message: "连接测试失败" };
  }
}

export async function testInline(params: {
  serviceType: string;
  host: string;
  port: number;
  password?: string | null;
  config?: Record<string, unknown>;
}): Promise<{ success: boolean; message: string }> {
  try {
    const socket = await Bun.connect({
      hostname: params.host,
      port: params.port,
      socket: {
        data() {},
        open(socket) { socket.end(); },
        error() {},
      },
    });
    socket.end();
    return { success: true, message: "连接测试成功" };
  } catch {
    return { success: false, message: "连接测试失败" };
  }
}

export function toResponse(service: typeof services.$inferSelect) {
  return {
    id: service.id,
    name: service.name,
    description: service.description,
    serviceType: service.serviceType,
    host: service.host,
    port: service.port,
    config: service.config,
    hasPassword: !!service.encryptedPassword,
    status: service.status,
    createdAt: service.createdAt.toISOString(),
    updatedAt: service.updatedAt.toISOString(),
  };
}
