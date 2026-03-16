import { z } from "zod";

// ── Project ──

export const projectSchema = z.object({
  name: z.string().min(1, "名称不能为空"),
  description: z.string().optional(),
});

export type ProjectFormData = z.infer<typeof projectSchema>;

// ── Connection ──

const sshSchema = z.object({
  type: z.literal("ssh"),
  name: z.string().min(1, "名称不能为空"),
  description: z.string().optional(),
  host: z.string().min(1, "主机地址不能为空"),
  port: z.coerce.number().int().min(1).max(65535).default(22),
  username: z.string().min(1, "用户名不能为空"),
  password: z.string().optional(),
  project_id: z.string().optional(),
});

const k8sSchema = z.object({
  type: z.literal("kubernetes"),
  name: z.string().min(1, "名称不能为空"),
  description: z.string().optional(),
  kubeconfig: z.string().min(1, "Kubeconfig 不能为空"),
  context: z.string().optional(),
  namespace: z.string().optional(),
  project_id: z.string().optional(),
});

export const connectionSchema = z.discriminatedUnion("type", [
  sshSchema,
  k8sSchema,
]);

export type ConnectionFormData = z.infer<typeof connectionSchema>;

// ── Service ──

export const serviceSchema = z.object({
  project_id: z.string().min(1, "项目不能为空"),
  name: z.string().min(1, "名称不能为空"),
  service_type: z.string().min(1, "服务类型不能为空"),
  description: z.string().optional(),
  business_context: z.string().optional(),
  owner: z.string().optional(),
  keywords: z.array(z.string()).optional(),
});

export type ServiceFormData = z.infer<typeof serviceSchema>;

// ── Document Paste ──

export const documentPasteSchema = z.object({
  filename: z.string().min(1, "文件名不能为空"),
  content: z.string().min(1, "内容不能为空"),
});

export type DocumentPasteFormData = z.infer<typeof documentPasteSchema>;

// ── SSE Events ──

const baseSSEFields = {
  timestamp: z.string(),
  phase: z.string().optional(),
  agent: z.string().optional(),
};

export const sseEventSchema = z.discriminatedUnion("event_type", [
  z.object({
    event_type: z.literal("thinking"),
    data: z.object({ content: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("tool_call"),
    data: z
      .object({ name: z.string(), args: z.record(z.string(), z.unknown()) })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("tool_result"),
    data: z
      .object({ name: z.string(), output: z.string() })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("approval_required"),
    data: z
      .object({
        approval_id: z.string(),
        tool_args: z.record(z.string(), z.unknown()),
      })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("ask_human"),
    data: z.object({ question: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("summary"),
    data: z.object({ summary_md: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("error"),
    data: z.object({ message: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
]);

export type SSEEventParsed = z.infer<typeof sseEventSchema>;
