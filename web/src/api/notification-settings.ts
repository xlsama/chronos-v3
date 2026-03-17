import { request } from "@/lib/request";

export interface NotificationSettings {
  id: string;
  platform: string;
  webhook_url: string;
  sign_key: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export function getNotificationSettings(platform: string) {
  return request<NotificationSettings | null>(
    `/notification-settings/${platform}`,
  );
}

export function upsertNotificationSettings(
  platform: string,
  data: { webhook_url: string; sign_key?: string; enabled: boolean },
) {
  return request<NotificationSettings>(
    `/notification-settings/${platform}`,
    { method: "PUT", body: data },
  );
}

export function testWebhook(data: {
  webhook_url: string;
  sign_key?: string;
  platform: "feishu";
}) {
  return request<{ success: boolean; message: string }>(
    `/notification-settings/test/webhook`,
    { method: "POST", body: data },
  );
}
