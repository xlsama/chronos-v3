import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as versionService from "@/service/version";

export const version = {
  list: authedProcedure
    .input(
      z.object({
        entityType: z.string(),
        entityId: z.string(),
      }),
    )
    .handler(async ({ input }) => {
      const versions = await versionService.listVersions(
        input.entityType,
        input.entityId,
      );
      return versions.map((v) => ({
        id: v.id,
        entityType: v.entityType,
        entityId: v.entityId,
        versionNumber: v.versionNumber,
        changeSource: v.changeSource,
        createdAt: v.createdAt.toISOString(),
      }));
    }),

  get: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      const version = await versionService.getVersion(input.id);
      if (!version) {
        throw new ORPCError("NOT_FOUND", { message: "Version not found" });
      }
      return {
        id: version.id,
        entityType: version.entityType,
        entityId: version.entityId,
        versionNumber: version.versionNumber,
        changeSource: version.changeSource,
        content: version.content,
        createdAt: version.createdAt.toISOString(),
      };
    }),
};
