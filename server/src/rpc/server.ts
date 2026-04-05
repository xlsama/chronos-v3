import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as serverService from "@/service/server";
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

const serverCreateSchema = z.object({
  name: z.string(),
  description: z.string().nullish(),
  host: z.string(),
  port: z.number().int().default(22),
  username: z.string().default("root"),
  password: z.string().nullish(),
  privateKey: z.string().nullish(),
  bastionHost: z.string().nullish(),
  bastionPort: z.number().int().nullish(),
  bastionUsername: z.string().nullish(),
  bastionPassword: z.string().nullish(),
  bastionPrivateKey: z.string().nullish(),
  sudoPassword: z.string().nullish(),
  useSshPasswordForSudo: z.boolean().default(true),
});

export const server = {
  create: authedProcedure
    .input(serverCreateSchema)
    .handler(async ({ input }) => {
      try {
        const s = await serverService.create(input);
        return serverService.toResponse(s);
      } catch (err) {
        mapError(err);
      }
    }),

  list: authedProcedure
    .input(
      z.object({
        page: z.number().int().positive().default(1),
        pageSize: z.number().int().positive().max(100).default(50),
      }),
    )
    .handler(async ({ input }) => {
      const result = await serverService.list(input.page, input.pageSize);
      return {
        items: result.items.map(serverService.toResponse),
        total: result.total,
        page: result.page,
        pageSize: result.pageSize,
      };
    }),

  get: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        const s = await serverService.get(input.id);
        return serverService.toResponse(s);
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
        host: z.string().optional(),
        port: z.number().int().optional(),
        username: z.string().optional(),
        password: z.string().nullish(),
        privateKey: z.string().nullish(),
        bastionHost: z.string().nullish(),
        bastionPort: z.number().int().nullish(),
        bastionUsername: z.string().nullish(),
        bastionPassword: z.string().nullish(),
        bastionPrivateKey: z.string().nullish(),
        sudoPassword: z.string().nullish(),
        useSshPasswordForSudo: z.boolean().optional(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const { id, ...data } = input;
        const s = await serverService.update(id, data);
        return serverService.toResponse(s);
      } catch (err) {
        mapError(err);
      }
    }),

  remove: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        await serverService.remove(input.id);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),

  test: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        return await serverService.testSavedServer(input.id);
      } catch (err) {
        mapError(err);
      }
    }),

  testInline: authedProcedure
    .input(
      z.object({
        host: z.string(),
        port: z.number().int().default(22),
        username: z.string().default("root"),
        password: z.string().nullish(),
        privateKey: z.string().nullish(),
      }),
    )
    .handler(async ({ input }) => {
      return serverService.testSSH(input);
    }),

  batchCreate: authedProcedure
    .input(z.object({ items: z.array(serverCreateSchema) }))
    .handler(async ({ input }) => {
      let created = 0;
      let skipped = 0;
      const errors: string[] = [];

      for (const item of input.items) {
        try {
          await serverService.create(item);
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
        "Batch create servers done",
      );
      return { created, skipped, errors };
    }),
};
