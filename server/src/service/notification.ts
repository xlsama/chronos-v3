import { db } from "@/db/connection";
import { notificationSettings } from "@/db/schema";
import { eq } from "drizzle-orm";
import { cryptoService } from "@/lib/crypto";
import { sendFeishuMessage } from "@/lib/feishu";
import { logger } from "@/lib/logger";

export async function getSettings(platform: string) {
  const [setting] = await db
    .select()
    .from(notificationSettings)
    .where(eq(notificationSettings.platform, platform));

  if (!setting) return null;

  return {
    id: setting.id,
    platform: setting.platform,
    webhookUrl: await cryptoService.decrypt(setting.encryptedWebhookUrl),
    signKey: setting.encryptedSignKey
      ? await cryptoService.decrypt(setting.encryptedSignKey)
      : null,
    enabled: setting.enabled,
    createdAt: setting.createdAt.toISOString(),
    updatedAt: setting.updatedAt.toISOString(),
  };
}

export async function upsert(
  platform: string,
  input: { webhookUrl: string; signKey?: string | null; enabled?: boolean },
) {
  const encryptedWebhookUrl = await cryptoService.encrypt(input.webhookUrl);
  const encryptedSignKey = input.signKey
    ? await cryptoService.encrypt(input.signKey)
    : null;

  const [existing] = await db
    .select()
    .from(notificationSettings)
    .where(eq(notificationSettings.platform, platform));

  let setting;
  if (existing) {
    [setting] = await db
      .update(notificationSettings)
      .set({
        encryptedWebhookUrl,
        encryptedSignKey,
        enabled: input.enabled ?? true,
      })
      .where(eq(notificationSettings.id, existing.id))
      .returning();
  } else {
    [setting] = await db
      .insert(notificationSettings)
      .values({
        platform,
        encryptedWebhookUrl,
        encryptedSignKey,
        enabled: input.enabled ?? true,
      })
      .returning();
  }

  return {
    id: setting.id,
    platform: setting.platform,
    webhookUrl: input.webhookUrl,
    signKey: input.signKey ?? null,
    enabled: setting.enabled,
    createdAt: setting.createdAt.toISOString(),
    updatedAt: setting.updatedAt.toISOString(),
  };
}

export async function testWebhook(
  webhookUrl: string,
  signKey?: string | null,
): Promise<{ success: boolean; message: string }> {
  try {
    await sendFeishuMessage(webhookUrl, "Chronos 测试消息 - 通知配置成功！", signKey);
    return { success: true, message: "测试消息发送成功" };
  } catch (e) {
    logger.warn({ error: String(e) }, "Webhook test failed");
    return { success: false, message: e instanceof Error ? e.message : String(e) };
  }
}
