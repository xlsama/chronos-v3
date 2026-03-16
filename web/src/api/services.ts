import { request } from "@/lib/request";
import type { Service } from "@/lib/types";

export function getServicesByProject(projectId: string) {
  return request<Service[]>(`/services/by-project/${projectId}`);
}

export function getServicesByConnection(connectionId: string) {
  return request<Service[]>(`/services/by-connection/${connectionId}`);
}

export function createService(data: {
  project_id: string;
  name: string;
  slug?: string;
  service_type?: string;
  description?: string;
  business_context?: string;
  owner?: string;
  keywords?: string[];
  status?: string;
  source?: string;
  metadata?: Record<string, unknown>;
}) {
  return request<Service>("/services", {
    method: "POST",
    body: data,
  });
}

export function updateService(
  id: string,
  data: Partial<{
    name: string;
    slug: string;
    service_type: string;
    description: string;
    business_context: string;
    owner: string;
    keywords: string[];
    status: string;
    source: string;
    metadata: Record<string, unknown>;
  }>,
) {
  return request<Service>(`/services/${id}`, {
    method: "PATCH",
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
