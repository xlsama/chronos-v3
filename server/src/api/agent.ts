import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { runAgent, resumeAgent } from "../ops-agent";
import type { ResumeInput } from "../ops-agent";

const agent = new Hono();

// POST /api/agent/:incidentId/run — 启动 Agent
agent.post(
  "/:incidentId/run",
  zValidator(
    "json",
    z.object({
      prompt: z.string().optional(),
    }),
  ),
  async (c) => {
    const incidentId = c.req.param("incidentId");
    const { prompt } = c.req.valid("json");

    return streamSSE(c, async (stream) => {
      const gen = runAgent(incidentId, prompt);
      for await (const event of gen) {
        await stream.writeSSE({
          event: event.type,
          data: JSON.stringify(event.data),
        });
      }
    });
  },
);

// POST /api/agent/:incidentId/resume — 恢复 Agent
agent.post(
  "/:incidentId/resume",
  zValidator(
    "json",
    z.discriminatedUnion("type", [
      z.object({
        type: z.literal("approval"),
        decision: z.enum(["approved", "rejected"]),
        feedback: z.string().optional(),
      }),
      z.object({
        type: z.literal("human_input"),
        text: z.string(),
      }),
      z.object({
        type: z.literal("confirm"),
        confirmed: z.boolean(),
        text: z.string().optional(),
      }),
    ]),
  ),
  async (c) => {
    const incidentId = c.req.param("incidentId");
    const input = c.req.valid("json") as ResumeInput;

    return streamSSE(c, async (stream) => {
      const gen = resumeAgent(incidentId, input);
      for await (const event of gen) {
        await stream.writeSSE({
          event: event.type,
          data: JSON.stringify(event.data),
        });
      }
    });
  },
);

export default agent;
