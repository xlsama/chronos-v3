import { os, ORPCError } from "@orpc/server";
import type { Context } from "./context";
import type { User } from "@/db/schema";
import { verifyTokenAndGetUser } from "@/lib/jwt";
import { AuthenticationError } from "@/lib/errors";

const base = os.$context<Context>();

export const publicProcedure = base;

export const authedProcedure = base.use(async ({ context, next }) => {
  try {
    const user = await verifyTokenAndGetUser(
      context.headers.get("authorization"),
    );
    return next({ context: { user } });
  } catch (err) {
    if (err instanceof AuthenticationError) {
      throw new ORPCError("UNAUTHORIZED", { message: err.message });
    }
    throw err;
  }
});

export type AuthedContext = Context & { user: User };
