export interface Server {
  id: string;
  name: string;
  description: string | null;
  host: string;
  port: number;
  username: string;
  status: string;
  authMethod: "password" | "private_key" | "none";
  hasBastion: boolean;
  bastionHost: string | null;
  createdAt: string;
  updatedAt: string;
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
  description: string;
  status: string;
  severity: string;
  summary_title: string | null;
  thread_id: string | null;
  saved_to_memory: boolean;
  is_archived: boolean;
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
  metadata_json: Record<string, unknown> | null;
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

export interface SSEEvent {
  event_id?: string;
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
  phase?: string;
  agent?: string;
  replay?: boolean;
}

export interface Service {
  id: string;
  name: string;
  description: string | null;
  serviceType: string;
  host: string;
  port: number;
  config: Record<string, unknown>;
  hasPassword: boolean;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface IncidentHistory {
  id: string;
  title: string;
  summary_md: string;
  occurrence_count: number;
  last_seen_at: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ContentVersion {
  id: string;
  entityType: string;
  entityId: string;
  versionNumber: number;
  changeSource: string;
  createdAt: string;
}

export interface ContentVersionDetail extends ContentVersion {
  content: string;
}

export type SeverityLevel = "P0" | "P1" | "P2" | "P3";
export type IncidentStatus = "open" | "investigating" | "resolved" | "stopped" | "interrupted";
