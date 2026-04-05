import type { RouterClient } from "@orpc/server";
import type { AppRouter } from "server/rpc";
import { createORPCClient, ORPCError, onError } from "@orpc/client";
import { RPCLink } from "@orpc/client/fetch";
import { createORPCReactQueryUtils } from "@orpc/react-query";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";

const link = new RPCLink({
  url: `${window.location.origin}/rpc`,
  headers: () => {
    const token = useAuthStore.getState().token;
    return token ? { authorization: `Bearer ${token}` } : {};
  },
  interceptors: [
    onError((error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;

      const message =
        error instanceof ORPCError
          ? error.message
          : error instanceof Error
            ? error.message
            : "Request failed";

      if (error instanceof ORPCError && error.code === "UNAUTHORIZED") {
        useAuthStore.getState().clearAuth();
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }

      toast.error(message);
    }),
  ],
});

export const client: RouterClient<AppRouter> = createORPCClient(link);

export const orpc = createORPCReactQueryUtils(client);
