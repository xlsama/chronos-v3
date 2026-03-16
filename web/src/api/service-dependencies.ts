import { request } from "@/lib/request";
import type { ServiceDependency } from "@/lib/types";

export function createServiceDependency(data: {
  project_id: string;
  from_service_id: string;
  to_service_id: string;
  dependency_type: string;
  description?: string;
  confidence?: number;
}) {
  return request<ServiceDependency>("/service-dependencies", {
    method: "POST",
    body: data,
  });
}

export function deleteServiceDependency(id: string) {
  return request(`/service-dependencies/${id}`, { method: "DELETE" });
}
