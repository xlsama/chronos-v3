import { client } from "@/lib/orpc";
import { request } from "@/lib/request";

// Types inferred from ORPC router
export type UserInfo = Awaited<ReturnType<typeof client.auth.me>>;
export type AuthResponse = Awaited<ReturnType<typeof client.auth.login>>;

// REST-based calls (file upload / static files)
export function uploadAvatar(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<UserInfo>("/auth/avatar", { method: "PUT", body: formData });
}

export function getAvatarUrl(filename: string): string {
  return `/api/auth/avatar/${filename}`;
}
