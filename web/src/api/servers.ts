import { request } from "@/lib/request";
import type { Server } from "@/lib/types";

export function getServers() {
  return request<Server[]>("/servers");
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
