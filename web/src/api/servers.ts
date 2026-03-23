import { request } from "@/lib/request";
import type { PaginatedResponse, Server } from "@/lib/types";

export function getServers(params?: { page?: number; page_size?: number }) {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const qs = searchParams.toString();
  return request<PaginatedResponse<Server>>(
    `/servers${qs ? `?${qs}` : ""}`,
  );
}

export function createServer(data: {
  name: string;
  description?: string;
  host: string;
  port?: number;
  username?: string;
  password?: string;
  private_key?: string;
  bastion_host?: string | null;
  bastion_port?: number | null;
  bastion_username?: string | null;
  bastion_password?: string | null;
  bastion_private_key?: string | null;
}) {
  return request<Server>("/servers", {
    method: "POST",
    body: data,
  });
}

export function updateServer(
  id: string,
  data: {
    name?: string;
    description?: string;
    host?: string;
    port?: number;
    username?: string;
    password?: string | null;
    private_key?: string | null;
    bastion_host?: string | null;
    bastion_port?: number | null;
    bastion_username?: string | null;
    bastion_password?: string | null;
    bastion_private_key?: string | null;
  },
) {
  return request<Server>(`/servers/${id}`, {
    method: "PATCH",
    body: data,
  });
}

export function deleteServer(id: string) {
  return request(`/servers/${id}`, { method: "DELETE" });
}

export function testServer(id: string) {
  return request<{ success: boolean; message: string }>(
    `/servers/${id}/test`,
    { method: "POST" },
  );
}

export interface BatchCreateResult {
  created: number;
  skipped: number;
  errors: string[];
}

export function batchCreateServers(
  items: Parameters<typeof createServer>[0][],
) {
  return request<BatchCreateResult>("/servers/batch", {
    method: "POST",
    body: { items },
  });
}
