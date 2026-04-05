import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { authedProcedure } from "./base";
import * as documentService from "@/service/document";
import * as versionService from "@/service/version";
import { NotFoundError, BadRequestError } from "@/lib/errors";
import { logger } from "@/lib/logger";

function mapError(err: unknown): never {
  if (err instanceof NotFoundError) {
    throw new ORPCError("NOT_FOUND", { message: err.message });
  }
  if (err instanceof BadRequestError) {
    throw new ORPCError("BAD_REQUEST", { message: err.message });
  }
  throw err;
}

export const document = {
  create: authedProcedure
    .input(
      z.object({
        projectId: z.string().uuid(),
        filename: z.string().min(1),
        content: z.string(),
        docType: z.string().default("markdown"),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const isEmpty = !input.content.trim();
        const doc = await documentService.save({
          projectId: input.projectId,
          filename: input.filename,
          content: input.content,
          docType: input.docType,
          status: isEmpty ? "indexed" : "pending",
        });

        // Save initial version for memory_config
        if (doc.docType === "memory_config") {
          await versionService.saveVersion(
            "memory_md",
            doc.id,
            input.content || "",
            "init",
          );
        }

        // Background indexing for non-empty content
        if (!isEmpty) {
          documentService
            .indexDocument(doc.id, input.projectId, input.content, null)
            .catch((err) => {
              logger.error(
                { err, documentId: doc.id },
                "Background indexing failed",
              );
            });
        }

        return documentService.toResponse(doc);
      } catch (err) {
        mapError(err);
      }
    }),

  listByProject: authedProcedure
    .input(z.object({ projectId: z.string().uuid() }))
    .handler(async ({ input }) => {
      const docs = await documentService.listByProject(input.projectId);
      return docs.map(documentService.toResponse);
    }),

  get: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        const doc = await documentService.get(input.id);
        return documentService.toDetailResponse(doc);
      } catch (err) {
        mapError(err);
      }
    }),

  update: authedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        content: z.string(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const doc = await documentService.get(input.id);

        // Save version for memory_config
        if (doc.docType === "memory_config") {
          await versionService.saveVersion(
            "memory_md",
            doc.id,
            input.content,
            "manual",
          );
        }

        const updated = await documentService.update(input.id, input.content);
        return documentService.toDetailResponse(updated);
      } catch (err) {
        mapError(err);
      }
    }),

  remove: authedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .handler(async ({ input }) => {
      try {
        await documentService.remove(input.id);
        return { ok: true as const };
      } catch (err) {
        mapError(err);
      }
    }),
};
