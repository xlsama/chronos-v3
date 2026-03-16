import { request } from "@/lib/request";
import type { Service } from "@/lib/types";

export function getServicesByInfra(infraId: string) {
  return request<Service[]>(`/services/by-infra/${infraId}`);
}

export function createService(data: {
  infrastructure_id: string;
  name: string;
  service_type: string;
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

export function discoverServices(infraId: string) {
  return request<{ discovered: number; services: Service[] }>(
    `/services/discover/${infraId}`,
    { method: "POST" },
  );
}
