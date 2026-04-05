import { app } from "@/main";

type JsonBody = Record<string, unknown> | unknown[];

export function request(
  method: string,
  path: string,
  options?: { body?: JsonBody; token?: string; formData?: FormData },
) {
  const headers: Record<string, string> = {};
  let reqBody: BodyInit | undefined;

  if (options?.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  if (options?.formData) {
    reqBody = options.formData;
  } else if (options?.body) {
    headers["Content-Type"] = "application/json";
    reqBody = JSON.stringify(options.body);
  }

  return app.request(path, { method, headers, body: reqBody });
}

export async function json<T = unknown>(res: Response): Promise<T> {
  return res.json() as Promise<T>;
}

export async function registerAndLogin(
  email = "test@test.com",
  password = "123456",
  name = "Test User",
) {
  await request("POST", "/api/auth/register", {
    body: { email, password, name },
  });
  const res = await request("POST", "/api/auth/login", {
    body: { email, password },
  });
  const data = await json<{ accessToken: string }>(res);
  return data.accessToken;
}
