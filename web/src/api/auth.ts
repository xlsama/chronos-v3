import { request } from "@/lib/request";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface UserInfo {
  id: string;
  email: string;
  name: string;
  avatar: string | null;
  is_active: boolean;
  created_at: string;
}

export function login(data: LoginRequest) {
  return request<AuthResponse>("/auth/login", { method: "POST", body: data });
}

export function register(data: RegisterRequest) {
  return request<UserInfo>("/auth/register", { method: "POST", body: data });
}

export function getMe() {
  return request<UserInfo>("/auth/me");
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export function uploadAvatar(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<UserInfo>("/auth/avatar", { method: "PUT", body: formData });
}

export function changePassword(data: ChangePasswordRequest) {
  return request<UserInfo>("/auth/password", { method: "PUT", body: data });
}

export function getAvatarUrl(filename: string): string {
  return `/api/auth/avatar/${filename}`;
}
