import { logger } from "@/lib/logger";

async function sign(timestamp: string, signKey: string): Promise<string> {
  const stringToSign = `${timestamp}\n${signKey}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(stringToSign),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new Uint8Array(0));
  return Buffer.from(signature).toString("base64");
}

export async function sendFeishuMessage(
  webhookUrl: string,
  text: string,
  signKey?: string | null,
): Promise<void> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const body: Record<string, unknown> = {
    msg_type: "text",
    content: { text },
  };

  if (signKey) {
    body.timestamp = timestamp;
    body.sign = await sign(timestamp, signKey);
  }

  const res = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = (await res.json()) as { code?: number; msg?: string };
  if (data.code !== 0) {
    logger.error({ code: data.code, msg: data.msg }, "Feishu webhook failed");
    throw new Error(data.msg || "Feishu webhook failed");
  }
}

export async function sendFeishuCard(
  webhookUrl: string,
  title: string,
  fields: Array<[string, string]>,
  color = "blue",
  signKey?: string | null,
): Promise<void> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const elements = fields.map(([label, value]) => ({
    tag: "div",
    text: { tag: "lark_md", content: `**${label}**\n${value}` },
  }));

  const body: Record<string, unknown> = {
    msg_type: "interactive",
    card: {
      header: {
        title: { tag: "plain_text", content: title },
        template: color,
      },
      elements,
    },
  };

  if (signKey) {
    body.timestamp = timestamp;
    body.sign = await sign(timestamp, signKey);
  }

  const res = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = (await res.json()) as { code?: number; msg?: string };
  if (data.code !== 0) {
    logger.error({ code: data.code, msg: data.msg }, "Feishu card webhook failed");
    throw new Error(data.msg || "Feishu card webhook failed");
  }
}
