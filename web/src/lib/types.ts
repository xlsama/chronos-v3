export interface Connection {
  id: string;
  name: string;
  type: string;
  description: string | null;
  host: string;
  port: number;
  username: string;
  status: string;
  capabilities: string[];
  scope_metadata: Record<string, unknown>;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Service {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  service_type: string;
  description: string | null;
  business_context: string | null;
  owner: string | null;
  keywords: string[];
  status: string;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ServiceDependency {
  id: string;
  project_id: string;
  from_service_id: string;
  to_service_id: string;
  dependency_type: string;
  description: string | null;
  confidence: number;
  created_at: string;
}

export interface ServiceConnectionBinding {
  id: string;
  project_id: string;
  service_id: string;
  connection_id: string;
  usage_type: string;
  priority: number;
  notes: string | null;
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
  created_at: string;
  updated_at: string;
}

export interface ProjectTopology {
  project: Project;
  services: Service[];
  dependencies: ServiceDependency[];
  connections: Connection[];
  bindings: ServiceConnectionBinding[];
}

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  doc_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ProjectDocumentDetail extends ProjectDocument {
  content: string;
}

export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "resolved" | "closed";
