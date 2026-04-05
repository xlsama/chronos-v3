import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as projectService from "@/service/project";
import { NotFoundError, ConflictError } from "@/lib/errors";

function mapError(err: unknown): never {
  if (err instanceof NotFoundError) {
    throw new ORPCError("NOT_FOUND", { message: err.message });
  }
  if (err instanceof ConflictError) {
    throw new ORPCError("CONFLICT", { message: err.message });
  }
  throw err;
}

export const project = {
  create: authedProcedure
    .input(
      z.object({
        name: z.string().min(1).max(255),
        description: z.string().nullish(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const p = await projectService.create(input);
        return projectService.toResponse(p);
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
      const result = await projectService.list(input.page, input.pageSize);
      return {
        items: result.items.map(projectService.toResponse),
        total: result.total,
        page: result.page,
        pageSize: result.pageSize,
      };
    }),

  get: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        const p = await projectService.get(input.id);
        return projectService.toResponse(p);
      } catch (err) {
        mapError(err);
      }
    }),

  update: authedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        name: z.string().min(1).max(255).optional(),
        description: z.string().nullish(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const { id, ...data } = input;
        const p = await projectService.update(id, data);
        return projectService.toResponse(p);
      } catch (err) {
        mapError(err);
      }
    }),

  remove: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        await projectService.remove(input.id);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),
};
