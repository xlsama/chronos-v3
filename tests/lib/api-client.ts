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

  async createServer(data: {
    name: string;
    description?: string;
    host: string;
    port?: number;
    username?: string;
    password?: string;
  }) {
    return this.api("/api/servers", { method: "POST", body: data });
  }

  async updateProject(
    projectId: string,
    data: { linked_server_ids?: string[] },
  ) {
    return this.api(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: data,
    });
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
