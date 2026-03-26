import { z } from "zod";

// ── Project ──

export const projectSchema = z.object({
  name: z.string().min(1, "名称不能为空"),
  description: z.string().optional(),
});

export type ProjectFormData = z.infer<typeof projectSchema>;

// ── Server ──

export const serverSchema = z
  .object({
    name: z.string().min(1, "名称不能为空"),
    description: z.string().optional(),
    host: z.string().min(1, "主机地址不能为空"),
    port: z.coerce.number().int().min(1).max(65535).default(22),
    username: z.string().min(1, "用户名不能为空"),
    auth_method: z.enum(["password", "private_key"]),
    password: z.string().optional(),
    private_key: z.string().optional(),
    use_bastion: z.boolean().default(false),
    bastion_host: z.string().optional(),
    bastion_port: z.coerce.number().int().min(1).max(65535).optional(),
    bastion_username: z.string().optional(),
    bastion_auth_method: z.enum(["password", "private_key"]).optional(),
    bastion_password: z.string().optional(),
    bastion_private_key: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.auth_method === "password" && !data.password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "密码不能为空",
        path: ["password"],
      });
    }
    if (data.auth_method === "private_key" && !data.private_key) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "私钥不能为空",
        path: ["private_key"],
      });
    }
    if (data.use_bastion) {
      if (!data.bastion_host) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "跳板机地址不能为空",
          path: ["bastion_host"],
        });
      }
      if (!data.bastion_username) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "跳板机用户名不能为空",
          path: ["bastion_username"],
        });
      }
      const bam = data.bastion_auth_method;
      if (bam === "password" && !data.bastion_password) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "跳板机密码不能为空",
          path: ["bastion_password"],
        });
      }
      if (bam === "private_key" && !data.bastion_private_key) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "跳板机私钥不能为空",
          path: ["bastion_private_key"],
        });
      }
    }
  });

export type ServerFormData = z.infer<typeof serverSchema>;

// ── Service ──

export const serviceSchema = z.object({
  name: z.string().min(1, "名称不能为空"),
  description: z.string().optional(),
  service_type: z.enum([
    "mysql",
    "postgresql",
    "redis",
    "prometheus",
    "mongodb",
    "elasticsearch",
    "doris",
    "starrocks",
    "jenkins",
    "kettle",
    "hive",
  ]),
  host: z.string().min(1, "主机地址不能为空"),
  port: z.coerce.number().int().min(1).max(65535),
  password: z.string().optional(),
  config: z.record(z.string(), z.unknown()).optional(),
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
  event_id: z.string().optional(),
  timestamp: z.string(),
  phase: z.string().optional(),
  agent: z.string().optional(),
  replay: z.boolean().optional(),
};

export const sseEventSchema = z.discriminatedUnion("event_type", [
  z.object({
    event_type: z.literal("thinking"),
    data: z.object({ content: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("tool_use"),
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
    event_type: z.literal("done"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("error"),
    data: z.object({ message: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("approval_decided"),
    data: z
      .object({
        approval_id: z.string(),
        decision: z.string(),
        decided_by: z.string(),
      })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("user_message"),
    data: z.object({ content: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("incident_stopped"),
    data: z.object({ reason: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("skill_read"),
    data: z
      .object({
        skill_name: z.string(),
        content: z.string(),
        skill_slug: z.string().optional(),
        success: z.boolean().optional(),
      })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("thinking_done"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("answer"),
    data: z.object({ content: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("answer_done"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("agent_status"),
    data: z.object({ status: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("ask_human_done"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("confirm_resolution_required"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("resolution_confirmed"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("agent_interrupted"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("planner_started"),
    data: z.object({}).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("planner_progress"),
    data: z.object({ status: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("plan_generated"),
    data: z.object({ plan_md: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("plan_updated"),
    data: z.object({ plan_md: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("round_started"),
    data: z
      .object({ round: z.number(), reason: z.string() })
      .passthrough(),
    ...baseSSEFields,
  }),
  z.object({
    event_type: z.literal("round_ended"),
    data: z.object({ round: z.number(), summary: z.string() }).passthrough(),
    ...baseSSEFields,
  }),
]);

export type SSEEventParsed = z.infer<typeof sseEventSchema>;
