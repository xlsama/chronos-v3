import { request } from "@/lib/request";

export interface BatchTestItem {
  id: string;
  name: string;
  type: "service" | "server";
  success: boolean;
  message: string;
}

export interface BatchTestResponse {
  results: BatchTestItem[];
  total: number;
  success_count: number;
  failure_count: number;
}

export function testAllConnections() {
  return request<BatchTestResponse>("/connections/test-all", {
    method: "POST",
  });
}
