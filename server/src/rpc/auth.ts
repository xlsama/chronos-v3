import { z } from "zod";
import { ORPCError } from "@orpc/server";
import { publicProcedure, authedProcedure } from "./base";
import * as authService from "@/service/auth";
import { AuthenticationError, ConflictError } from "@/lib/errors";

function userResponse(user: {
  id: string;
  email: string;
  name: string;
  avatar: string | null;
  isActive: boolean;
  createdAt: Date;
}) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    avatar: user.avatar,
    isActive: user.isActive,
    createdAt: user.createdAt.toISOString(),
  };
}

function mapError(err: unknown): never {
  if (err instanceof AuthenticationError) {
    throw new ORPCError("UNAUTHORIZED", { message: err.message });
  }
  if (err instanceof ConflictError) {
    throw new ORPCError("CONFLICT", { message: err.message });
  }
  console.error("[rpc/auth] unhandled error:", err);
  throw err;
}

export const auth = {
  register: publicProcedure
    .input(
      z.object({
        email: z.email(),
        password: z.string().min(6),
        name: z.string().min(1).max(255),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const user = await authService.register(input.email, input.password, input.name);
        return userResponse(user);
      } catch (err) {
        mapError(err);
      }
    }),

  login: publicProcedure
    .input(
      z.object({
        email: z.email(),
        password: z.string(),
      }),
    )
    .handler(async ({ input }) => {
      try {
        const user = await authService.authenticate(input.email, input.password);
        const accessToken = await authService.generateToken(user.id, user.email);
        return { accessToken, tokenType: "bearer" as const };
      } catch (err) {
        mapError(err);
      }
    }),

  me: authedProcedure.handler(async ({ context }) => {
    return userResponse(context.user);
  }),

  changePassword: authedProcedure
    .input(
      z.object({
        oldPassword: z.string(),
        newPassword: z.string().min(6),
      }),
    )
    .handler(async ({ input, context }) => {
      try {
        const updated = await authService.changePassword(
          context.user.id,
          input.oldPassword,
          input.newPassword,
        );
        return userResponse(updated);
      } catch (err) {
        mapError(err);
      }
    }),
};
