import {
  boolean,
  customType,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from "drizzle-orm/pg-core";

// pgvector custom type
const vector = customType<{ data: number[]; driverParam: string }>({
  dataType() {
    return "vector(1024)";
  },
  toDriver(value: number[]) {
    return `[${value.join(",")}]`;
  },
  fromDriver(value: unknown) {
    return (value as string).slice(1, -1).split(",").map(Number);
  },
});

// ─── Users ───────────────────────────────────────────────

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: varchar("email", { length: 255 }).notNull().unique(),
  hashedPassword: text("hashed_password").notNull(),
  name: varchar("name", { length: 255 }).notNull(),
  avatar: varchar("avatar", { length: 500 }),
  isActive: boolean("is_active").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow()
    .$onUpdate(() => new Date()),
});

// ─── Projects ────────────────────────────────────────────

export const projects = pgTable("projects", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: varchar("name", { length: 255 }).notNull(),
  slug: varchar("slug", { length: 255 }).notNull().unique(),
  description: text("description"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow()
    .$onUpdate(() => new Date()),
});

// ─── Servers ─────────────────────────────────────────────

export const servers = pgTable(
  "servers",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    name: varchar("name", { length: 255 }).notNull(),
    description: text("description"),
    host: varchar("host", { length: 255 }).notNull().default(""),
    port: integer("port").notNull().default(22),
    username: varchar("username", { length: 100 }).notNull().default("root"),
    encryptedPassword: text("encrypted_password"),
    encryptedPrivateKey: text("encrypted_private_key"),
    bastionHost: varchar("bastion_host", { length: 255 }),
    bastionPort: integer("bastion_port"),
    bastionUsername: varchar("bastion_username", { length: 100 }),
    encryptedBastionPassword: text("encrypted_bastion_password"),
    encryptedBastionPrivateKey: text("encrypted_bastion_private_key"),
    encryptedSudoPassword: text("encrypted_sudo_password"),
    useSshPasswordForSudo: boolean("use_ssh_password_for_sudo").notNull().default(true),
    status: varchar("status", { length: 20 }).notNull().default("unknown"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [uniqueIndex("uq_servers_name").on(table.name)],
);

// ─── Services ────────────────────────────────────────────

export const services = pgTable(
  "services",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    name: varchar("name", { length: 255 }).notNull(),
    description: text("description"),
    serviceType: varchar("service_type", { length: 50 }).notNull(),
    host: varchar("host", { length: 255 }).notNull(),
    port: integer("port").notNull(),
    config: jsonb("config").notNull().default({}),
    encryptedPassword: text("encrypted_password"),
    status: varchar("status", { length: 20 }).notNull().default("unknown"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [uniqueIndex("uq_services_name").on(table.name)],
);

// ─── Incidents ───────────────────────────────────────────

export const incidents = pgTable("incidents", {
  id: uuid("id").primaryKey().defaultRandom(),
  description: text("description").notNull(),
  status: varchar("status", { length: 20 }).notNull().default("open"),
  // open | resolved | closed — 业务状态，和 agent_sessions.status 独立
  severity: varchar("severity", { length: 20 }).notNull().default("P3"),
  summaryTitle: varchar("summary_title", { length: 500 }),
  savedToMemory: boolean("saved_to_memory").notNull().default(false),
  isArchived: boolean("is_archived").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow()
    .$onUpdate(() => new Date()),
});

// ─── Attachments ─────────────────────────────────────────

export const attachments = pgTable(
  "attachments",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id").references(() => incidents.id, {
      onDelete: "cascade",
    }),
    filename: varchar("filename", { length: 500 }).notNull(),
    storedFilename: varchar("stored_filename", { length: 500 }).notNull(),
    contentType: varchar("content_type", { length: 255 }).notNull(),
    size: integer("size").notNull(),
    parsedContent: text("parsed_content"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [index("ix_attachments_incident_id").on(table.incidentId)],
);

// ─── Project Documents ──────────────────────────────────

export const projectDocuments = pgTable(
  "project_documents",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    filename: varchar("filename", { length: 500 }).notNull(),
    content: text("content").notNull(),
    docType: varchar("doc_type", { length: 50 }).notNull(),
    status: varchar("status", { length: 20 }).notNull().default("pending"),
    errorMessage: text("error_message"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [index("ix_project_documents_project_id").on(table.projectId)],
);

// ─── Document Chunks ─────────────────────────────────────

export const documentChunks = pgTable(
  "document_chunks",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    documentId: uuid("document_id")
      .notNull()
      .references(() => projectDocuments.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    chunkIndex: integer("chunk_index").notNull(),
    content: text("content").notNull(),
    embedding: vector("embedding"),
    metadata: jsonb("metadata").notNull().default({}),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index("ix_document_chunks_document_id").on(table.documentId),
    index("ix_document_chunks_project_id").on(table.projectId),
  ],
);

// ─── Messages ────────────────────────────────────────────

export const messages = pgTable(
  "messages",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id),
    role: varchar("role", { length: 20 }).notNull(),
    eventType: varchar("event_type", { length: 50 }).notNull(),
    content: text("content").notNull(),
    metadataJson: jsonb("metadata_json"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index("ix_messages_incident_id").on(table.incidentId),
    index("ix_messages_incident_created").on(table.incidentId, table.createdAt),
  ],
);

// ─── Approval Requests ──────────────────────────────────

export const approvalRequests = pgTable(
  "approval_requests",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id),
    toolName: varchar("tool_name", { length: 100 }).notNull(),
    toolArgs: text("tool_args").notNull(),
    decision: varchar("decision", { length: 20 }),
    decidedBy: varchar("decided_by", { length: 100 }),
    decidedAt: timestamp("decided_at", { withTimezone: true }),
    riskLevel: varchar("risk_level", { length: 20 }),
    riskDetail: text("risk_detail"),
    explanation: text("explanation"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [index("ix_approval_requests_incident_id").on(table.incidentId)],
);

// ─── Notification Settings ──────────────────────────────

export const notificationSettings = pgTable(
  "notification_settings",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    platform: varchar("platform", { length: 50 }).notNull().unique(),
    encryptedWebhookUrl: text("encrypted_webhook_url").notNull(),
    encryptedSignKey: text("encrypted_sign_key"),
    enabled: boolean("enabled").notNull().default(true),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [uniqueIndex("uq_notification_settings_platform").on(table.platform)],
);

// ─── Content Versions ───────────────────────────────────

export const contentVersions = pgTable(
  "content_versions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    entityType: varchar("entity_type", { length: 50 }).notNull(),
    entityId: varchar("entity_id", { length: 255 }).notNull(),
    content: text("content").notNull(),
    versionNumber: integer("version_number").notNull(),
    changeSource: varchar("change_source", { length: 50 }).notNull().default("manual"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index("ix_content_versions_entity").on(table.entityType, table.entityId, table.versionNumber),
  ],
);

// ─── Incident History ───────────────────────────────────

export const incidentHistory = pgTable("incident_history", {
  id: uuid("id").primaryKey().defaultRandom(),
  title: varchar("title", { length: 500 }).notNull(),
  summaryMd: text("summary_md").notNull(),
  embedding: vector("embedding"),
  occurrenceCount: integer("occurrence_count").notNull().default(1),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).notNull().defaultNow(),
});

// ─── Agent Sessions ────────────────────────────────────

export const agentSessions = pgTable(
  "agent_sessions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id, { onDelete: "cascade" })
      .unique(),

    status: varchar("status", { length: 20 }).notNull().default("running"),

    // 核心状态
    agentMessages: jsonb("agent_messages").notNull().default([]),
    turnCount: integer("turn_count").notNull().default(0),
    maxTurns: integer("max_turns").notNull().default(40),

    // Plan & Compact
    planMd: text("plan_md"),
    compactMd: text("compact_md"),
    summary: text("summary"),

    // 中断恢复
    pendingToolCall: jsonb("pending_tool_call"),
    pendingApprovalId: uuid("pending_approval_id"),
    interruptedAt: timestamp("interrupted_at", { withTimezone: true }),

    // 时间戳
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [
    index("ix_agent_sessions_incident_id").on(table.incidentId),
    index("ix_agent_sessions_status").on(table.status),
  ],
);

// ─── Type Exports ───────────────────────────────────────

export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;
export type Incident = typeof incidents.$inferSelect;
export type NewIncident = typeof incidents.$inferInsert;
export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
export type Server = typeof servers.$inferSelect;
export type Service = typeof services.$inferSelect;
export type Project = typeof projects.$inferSelect;
export type ApprovalRequest = typeof approvalRequests.$inferSelect;
export type IncidentHistoryRecord = typeof incidentHistory.$inferSelect;
export type AgentSessionRecord = typeof agentSessions.$inferSelect;
