import { request } from "@/lib/request";
import type { Connection } from "@/lib/types";

export function getConnections() {
  return request<Connection[]>("/connections");
}

export function createConnection(data: {
  name: string;
  type?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  private_key?: string;
  kubeconfig?: string;
  context?: string;
  namespace?: string;
}) {
  return request<Connection>("/connections", {
    method: "POST",
    body: data,
  });
}

export function deleteConnection(id: string) {
  return request(`/connections/${id}`, { method: "DELETE" });
}

export function testConnection(id: string) {
  return request<{ success: boolean; message: string }>(
    `/connections/${id}/test`,
    { method: "POST" },
  );
}
