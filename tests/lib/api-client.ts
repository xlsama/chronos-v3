import { ofetch, type FetchOptions } from "ofetch";

const BASE = "http://localhost:8000";

export class ApiClient {
  private api = ofetch.create({
    baseURL: BASE,
    onResponseError({ response }) {
      console.error(
        `[api] ${response.status} ${response.url}`,
        JSON.stringify(response._data, null, 2),
      );
    },
  });

  async createProject(data: { name: string; description?: string }) {
    return this.api("/api/projects", { method: "POST", body: data });
  }

  async createConnection(data: {
    name: string;
    host: string;
    port: number;
    username: string;
    password: string;
    project_id: string;
  }) {
    return this.api("/api/connections", { method: "POST", body: data });
  }

  async createService(data: {
    name: string;
    service_type: string;
    project_id: string;
    description?: string;
    business_context?: string;
    keywords?: string[];
  }) {
    return this.api("/api/services", { method: "POST", body: data });
  }

  async createDependency(data: {
    project_id: string;
    from_service_id: string;
    to_service_id: string;
    dependency_type?: string;
    description?: string;
    confidence?: number;
  }) {
    return this.api("/api/service-dependencies", { method: "POST", body: data });
  }

  async createBinding(data: {
    service_id: string;
    connection_id: string;
    project_id: string;
  }) {
    return this.api("/api/service-bindings", { method: "POST", body: data });
  }

  async getIncident(incidentId: string) {
    return this.api(`/api/incidents/${incidentId}`);
  }

  async decideApproval(approvalId: string, decision: "approved" | "rejected") {
    return this.api(`/api/approvals/${approvalId}/decide`, {
      method: "POST",
      body: { decision, decided_by: "e2e-test" },
    });
  }
}
