export interface Server {
  id: string;
  name: string;
  description: string | null;
  host: string;
  port: number;
  username: string;
  status: string;
  auth_method: "password" | "private_key" | "none";
  has_bastion: boolean;
  bastion_host: string | null;
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
  description: string;
  status: string;
  severity: string;
  summary_md: string | null;
  summary_title: string | null;
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
  service_type: string;
  host: string;
  port: number;
  config: Record<string, unknown>;
  has_password: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
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

export interface IncidentHistory {
  id: string;
  title: string;
  summary_md: string;
  occurrence_count: number;
  last_seen_at: string;
  created_at: string;
}

export interface Skill {
  slug: string;
  name: string;
  description: string;
  has_scripts: boolean;
  has_references: boolean;
  has_assets: boolean;
  draft: boolean;
  created_at: string;
  updated_at: string;
}

export interface SkillDetail extends Skill {
  content: string;
  script_files: string[];
  reference_files: string[];
  asset_files: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ContentVersion {
  id: string;
  entity_type: string;
  entity_id: string;
  version_number: number;
  change_source: string;
  created_at: string;
}

export interface ContentVersionDetail extends ContentVersion {
  content: string;
}

export type SeverityLevel = "P0" | "P1" | "P2" | "P3";
export type IncidentStatus = "open" | "investigating" | "resolved" | "stopped";
