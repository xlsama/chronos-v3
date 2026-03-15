export interface Infrastructure {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  status: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Incident {
  id: string;
  title: string;
  description: string;
  status: string;
  severity: string;
  infrastructure_id: string | null;
  project_id: string | null;
  summary_md: string | null;
  thread_id: string | null;
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

// SSE event types
export interface SSEEvent {
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "resolved" | "closed";
