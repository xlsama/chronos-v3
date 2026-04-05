import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as skillService from "@/service/skill";
import * as versionService from "@/service/version";

function mapError(err: unknown): never {
  if (err instanceof Error) {
    const msg = err.message;
    if (msg.includes("not found")) {
      throw new ORPCError("NOT_FOUND", { message: msg });
    }
    if (msg.includes("already exists")) {
      throw new ORPCError("CONFLICT", { message: msg });
    }
    if (
      msg.includes("非法") ||
      msg.includes("路径必须在") ||
      msg.includes("格式不正确")
    ) {
      throw new ORPCError("BAD_REQUEST", { message: msg });
    }
  }
  throw err;
}

export const skill = {
  list: authedProcedure.handler(async () => {
    const skills = await skillService.listSkills();
    return skills.map(skillService.toResponse);
  }),

  get: authedProcedure
    .input(z.object({ slug: z.string() }))
    .handler(async ({ input }) => {
      try {
        const { meta, content } = await skillService.getSkill(input.slug);
        return skillService.toDetailResponse(meta, content);
      } catch (err) {
        mapError(err);
      }
    }),

  create: authedProcedure
    .input(z.object({ slug: z.string() }))
    .handler(async ({ input }) => {
      try {
        const meta = await skillService.createSkill(input.slug);
        const { content } = await skillService.getSkill(input.slug);
        await versionService.saveVersion("skill", input.slug, content, "init");
        return skillService.toResponse(meta);
      } catch (err) {
        mapError(err);
      }
    }),

  update: authedProcedure
    .input(z.object({ slug: z.string(), content: z.string() }))
    .handler(async ({ input }) => {
      try {
        const meta = await skillService.updateSkill(input.slug, input.content);
        await versionService.saveVersion(
          "skill",
          input.slug,
          input.content,
          "manual",
        );
        return skillService.toResponse(meta);
      } catch (err) {
        mapError(err);
      }
    }),

  remove: authedProcedure
    .input(z.object({ slug: z.string() }))
    .handler(async ({ input }) => {
      try {
        await skillService.deleteSkill(input.slug);
        await versionService.deleteVersions("skill", input.slug);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),

  getFile: authedProcedure
    .input(z.object({ slug: z.string(), path: z.string().min(1) }))
    .handler(async ({ input }) => {
      try {
        const content = await skillService.readSkillFile(
          input.slug,
          input.path,
        );
        return { content };
      } catch (err) {
        mapError(err);
      }
    }),

  putFile: authedProcedure
    .input(
      z.object({
        slug: z.string(),
        path: z.string().min(1),
        content: z.string(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        await skillService.writeSkillFile(
          input.slug,
          input.path,
          input.content,
        );
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),

  deleteFile: authedProcedure
    .input(z.object({ slug: z.string(), path: z.string().min(1) }))
    .handler(async ({ input }) => {
      try {
        await skillService.deleteSkillFile(input.slug, input.path);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),
};
