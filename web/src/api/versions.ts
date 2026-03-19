import { request } from "@/lib/request";
import type { ContentVersion, ContentVersionDetail } from "@/lib/types";

export function getVersions(entityType: string, entityId: string) {
  return request<ContentVersion[]>(
    `/versions?entity_type=${entityType}&entity_id=${entityId}`,
  );
}

export function getVersion(versionId: string) {
  return request<ContentVersionDetail>(`/versions/${versionId}`);
}
