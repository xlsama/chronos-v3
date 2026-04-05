import { z } from "zod";
import { authedProcedure } from "./base";
import * as notificationService from "@/service/notification";

export const notification = {
  get: authedProcedure
    .input(z.object({ platform: z.string() }))
    .handler(async ({ input }) => {
      return notificationService.getSettings(input.platform);
    }),

  upsert: authedProcedure
    .input(
      z.object({
        platform: z.string(),
        webhookUrl: z.string(),
        signKey: z.string().nullish(),
        enabled: z.boolean().default(true),
      }),
    )
    .handler(async ({ input }) => {
      const { platform, ...data } = input;
      return notificationService.upsert(platform, data);
    }),

  testWebhook: authedProcedure
    .input(
      z.object({
        webhookUrl: z.string(),
        signKey: z.string().nullish(),
      }),
    )
    .handler(async ({ input }) => {
      return notificationService.testWebhook(input.webhookUrl, input.signKey);
    }),
};
