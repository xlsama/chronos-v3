export interface Connection {
  id: string;
  name: string;
  type: string; // ssh, kubernetes
  host: string;
  port: number;
  username: string;
  status: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Service {
  id: string;
  connection_id: string;
  name: string;
  port: number | null;
  namespace: string | null;
  status: string;
  discovery_method: string;
  created_at: string;
  updated_at: string;
}

export interface MonitoringSource {
  id: string;
  project_id: string;
  name: string;
  source_type: string;
  endpoint: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Attachment {
  id: string;
  incident_id: string | null;
  filename: string;
  stored_filename: string;
  content_type: string;
  size: number;
  created_at: string;
}

export interface Incident {
  id: string;
  title: string;
  description: string;
  status: string;
  severity: string;
  connection_id: string | null;
  project_id: string | null;
  summary_md: string | null;
  thread_id: string | null;
  saved_to_memory: boolean;
  attachments?: Attachment[];
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  incident_id: string;
  role: string;
  event_type: string;
  content: string;
  metadata_json: string | null;
  created_at: string;
}

export interface ApprovalRequest {
  id: string;
  incident_id: string;
  tool_name: string;
  tool_args: string;
  decision: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

// SSE event types — canonical shape kept for runtime compatibility.
// Validated at parse time via sseEventSchema in lib/schemas.ts.
export interface SSEEvent {
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
  phase?: string;
  agent?: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  service_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  doc_type: string;
  status: string;
  created_at: string;
}

export interface ProjectDocumentDetail extends ProjectDocument {
  content: string;
}

export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "resolved" | "closed";
