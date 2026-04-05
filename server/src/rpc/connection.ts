import { authedProcedure } from "./base";
import { db } from "@/db/connection";
import { servers, services } from "@/db/schema";
import * as serverService from "@/service/server";
import * as serviceService from "@/service/service";

export const connection = {
  testAll: authedProcedure.handler(async () => {
    const allServers = await db.select().from(servers);
    const allServices = await db.select().from(services);

    const results = await Promise.allSettled([
      ...allServers.map(async (s) => {
        const result = await serverService.testSavedServer(s.id);
        return {
          id: s.id,
          name: s.name,
          type: "server" as const,
          ...result,
        };
      }),
      ...allServices.map(async (s) => {
        const result = await serviceService.testConnection(s.id);
        return {
          id: s.id,
          name: s.name,
          type: "service" as const,
          ...result,
        };
      }),
    ]);

    const items = results.map((r) => {
      if (r.status === "fulfilled") return r.value;
      return {
        id: "",
        name: "",
        type: "server" as const,
        success: false,
        message: String(r.reason),
      };
    });

    const successCount = items.filter((i) => i.success).length;
    return {
      results: items,
      total: items.length,
      successCount,
      failureCount: items.length - successCount,
    };
  }),
};
