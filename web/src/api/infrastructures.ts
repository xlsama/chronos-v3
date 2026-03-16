import { request } from "@/lib/request";
import type { Infrastructure } from "@/lib/types";

export function getInfrastructures() {
  return request<Infrastructure[]>("/infrastructures");
}

export function createInfrastructure(data: {
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
  return request<Infrastructure>("/infrastructures", {
    method: "POST",
    body: data,
  });
}

export function deleteInfrastructure(id: string) {
  return request(`/infrastructures/${id}`, { method: "DELETE" });
}

export function testInfrastructure(id: string) {
  return request<{ success: boolean; message: string }>(
    `/infrastructures/${id}/test`,
    { method: "POST" },
  );
}
