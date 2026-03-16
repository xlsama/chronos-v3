import { request } from "@/lib/request";
import type { ServiceConnectionBinding } from "@/lib/types";

export function createServiceBinding(data: {
  project_id: string;
  service_id: string;
  connection_id: string;
  usage_type: string;
  priority?: number;
  notes?: string;
}) {
  return request<ServiceConnectionBinding>("/service-bindings", {
    method: "POST",
    body: data,
  });
}

export function deleteServiceBinding(id: string) {
  return request(`/service-bindings/${id}`, { method: "DELETE" });
}
