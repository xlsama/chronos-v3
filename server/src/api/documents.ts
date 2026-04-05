import { Hono } from "hono";
import { join } from "path";
import { authMiddleware } from "@/lib/jwt";
import { knowledgeDir } from "@/lib/paths";
import { NotFoundError, BadRequestError } from "@/lib/errors";
import { db } from "@/db/connection";
import { projects } from "@/db/schema";
import { eq } from "drizzle-orm";
import * as documentService from "@/service/document";

// File upload: POST /api/projects/:projectId/documents/upload
// File download: GET /api/documents/:id/file
const app = new Hono();
app.use("*", authMiddleware);

app.post("/projects/:projectId/documents/upload", async (c) => {
  const projectId = c.req.param("projectId");
  const formData = await c.req.formData();
  const file = formData.get("file");
  if (!(file instanceof File)) {
    throw new BadRequestError("缺少文件");
  }

  const doc = await documentService.saveUploadedFile(projectId, file);
  return c.json(documentService.toResponse(doc), 201);
});

app.get("/documents/:id/file", async (c) => {
  const doc = await documentService.get(c.req.param("id"));
  const [project] = await db
    .select()
    .from(projects)
    .where(eq(projects.id, doc.projectId));
  if (!project) throw new NotFoundError("Project not found");

  const filePath = join(knowledgeDir(project.slug), doc.filename);
  const file = Bun.file(filePath);
  if (!(await file.exists())) {
    throw new NotFoundError("File not found on disk");
  }

  return new Response(file, {
    headers: {
      "Content-Type": file.type,
      "Content-Disposition": `inline; filename="${doc.filename}"`,
    },
  });
});

export default app;
