import { request } from "@/lib/request";
import type { Service } from "@/lib/types";

export function getServicesByConnection(connectionId: string) {
  return request<Service[]>(`/services/by-connection/${connectionId}`);
}

export function createService(data: {
  connection_id: string;
  name: string;
  port?: number;
  namespace?: string;
}) {
  return request<Service>("/services", {
    method: "POST",
    body: data,
  });
}

export function deleteService(id: string) {
  return request(`/services/${id}`, { method: "DELETE" });
}

export function discoverServices(connectionId: string) {
  return request<{ discovered: number; services: Service[] }>(
    `/services/discover/${connectionId}`,
    { method: "POST" },
  );
}
