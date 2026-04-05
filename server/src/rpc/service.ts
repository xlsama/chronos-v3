import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as serviceService from "@/service/service";
import { NotFoundError, ValidationError } from "@/lib/errors";
import { logger } from "@/lib/logger";

function mapError(err: unknown): never {
  if (err instanceof NotFoundError) {
    throw new ORPCError("NOT_FOUND", { message: err.message });
  }
  if (err instanceof ValidationError) {
    throw new ORPCError("BAD_REQUEST", { message: err.message });
  }
  throw err;
}

const serviceCreateSchema = z.object({
  name: z.string(),
  description: z.string().nullish(),
  serviceType: z.string(),
  host: z.string(),
  port: z.number().int(),
  password: z.string().nullish(),
  config: z.record(z.string(), z.unknown()).optional(),
});

export const service = {
  create: authedProcedure
    .input(serviceCreateSchema)
    .handler(async ({ input }) => {
      try {
        const s = await serviceService.create(input);
        return serviceService.toResponse(s);
      } catch (err) {
        mapError(err);
      }
    }),

  list: authedProcedure
    .input(
      z.object({
        page: z.number().int().positive().default(1),
        pageSize: z.number().int().positive().max(100).default(50),
        serviceType: z.string().optional(),
      }),
    )
    .handler(async ({ input }) => {
      const result = await serviceService.list(
        input.page,
        input.pageSize,
        input.serviceType,
      );
      return {
        items: result.items.map(serviceService.toResponse),
        total: result.total,
        page: result.page,
        pageSize: result.pageSize,
      };
    }),

  get: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        const s = await serviceService.get(input.id);
        return serviceService.toResponse(s);
      } catch (err) {
        mapError(err);
      }
    }),

  update: authedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        name: z.string().optional(),
        description: z.string().nullish(),
        serviceType: z.string().optional(),
        host: z.string().optional(),
        port: z.number().int().optional(),
        password: z.string().nullish(),
        config: z.record(z.string(), z.unknown()).optional(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const { id, ...data } = input;
        const s = await serviceService.update(id, data);
        return serviceService.toResponse(s);
      } catch (err) {
        mapError(err);
      }
    }),

  remove: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        await serviceService.remove(input.id);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),

  test: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        return await serviceService.testConnection(input.id);
      } catch (err) {
        mapError(err);
      }
    }),

  testInline: authedProcedure
    .input(
      z.object({
        serviceType: z.string(),
        host: z.string(),
        port: z.number().int(),
        password: z.string().nullish(),
        config: z.record(z.string(), z.unknown()).optional(),
      }),
    )
    .handler(async ({ input }) => {
      return serviceService.testInline(input);
    }),

  batchCreate: authedProcedure
    .input(z.object({ items: z.array(serviceCreateSchema) }))
    .handler(async ({ input }) => {
      let created = 0;
      let skipped = 0;
      const errors: string[] = [];

      for (const item of input.items) {
        try {
          await serviceService.create(item);
          created++;
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message.toLowerCase() : "";
          if (
            msg.includes("already exists") ||
            msg.includes("unique") ||
            msg.includes("duplicate")
          ) {
            skipped++;
          } else {
            errors.push(
              `${item.name}: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        }
      }

      logger.info(
        { created, skipped, errors: errors.length },
        "Batch create services done",
      );
      return { created, skipped, errors };
    }),
};
