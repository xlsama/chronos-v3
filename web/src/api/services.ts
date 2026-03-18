import { request } from "@/lib/request";
import type { PaginatedResponse, Service } from "@/lib/types";

export function getServices(params?: {
  page?: number;
  page_size?: number;
  type?: string;
}) {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size)
    searchParams.set("page_size", String(params.page_size));
  if (params?.type) searchParams.set("type", params.type);
  const qs = searchParams.toString();
  return request<PaginatedResponse<Service>>(
    `/services${qs ? `?${qs}` : ""}`,
  );
}

export function createService(data: {
  name: string;
  description?: string;
  service_type: string;
  host: string;
  port: number;
  password?: string;
  config?: Record<string, unknown>;
}) {
  return request<Service>("/services", {
    method: "POST",
    body: data,
  });
}

export function updateService(
  id: string,
  data: {
    name?: string;
    description?: string;
    service_type?: string;
    host?: string;
    port?: number;
    password?: string | null;
    config?: Record<string, unknown>;
  },
) {
  return request<Service>(`/services/${id}`, {
    method: "PATCH",
    body: data,
  });
}

export function deleteService(id: string) {
  return request(`/services/${id}`, { method: "DELETE" });
}

export function testService(id: string) {
  return request<{ success: boolean; message: string }>(
    `/services/${id}/test`,
    { method: "POST" },
  );
}
