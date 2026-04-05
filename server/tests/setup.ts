import { db } from "@/db/connection";
import { sql } from "drizzle-orm";
import { afterAll, beforeEach } from "bun:test";

// Clean all tables before each test
beforeEach(async () => {
  await db.execute(sql`TRUNCATE TABLE
    agent_sessions, content_versions, document_chunks, project_documents,
    approval_requests, messages, attachments,
    notification_settings, incident_history, incidents,
    servers, services, projects, users
    CASCADE`);
});

afterAll(async () => {
  // cleanup if needed
});
