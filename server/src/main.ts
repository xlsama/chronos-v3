import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger as honoLogger } from "hono/logger";
import { env } from "@/env";
import { errorHandler } from "@/lib/errors";
import { logger } from "@/lib/logger";
import { rpcHandler } from "@/rpc/handler";
import auth from "@/api/auth";
import documents from "@/api/documents";
import agent from "@/api/agent";

const app = new Hono();

// Middleware
app.use(
  "*",
  cors({
    origin: "*",
    allowMethods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization"],
    credentials: true,
  }),
);
app.use("*", honoLogger());

// Global error handler
app.onError(errorHandler);

// Health check
app.get("/health", (c) => c.json({ status: "ok" }));

// ORPC handler
app.use("/rpc/*", async (c, next) => {
  const { matched, response } = await rpcHandler.handle(c.req.raw, {
    prefix: "/rpc",
    context: { headers: c.req.raw.headers },
  });
  if (matched) {
    return c.newResponse(response.body, response);
  }
  await next();
});

// REST API routes (file upload/download only)
app.route("/api/auth", auth);
app.route("/api", documents);
app.route("/api/agent", agent);

export { app };

logger.info({ port: env.PORT }, "Starting Chronos server");

export default {
  port: env.PORT,
  fetch: app.fetch,
};
