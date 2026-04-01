import { ofetch, FetchError, type FetchOptions } from "ofetch";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function request<T>(
  url: string,
  options?: FetchOptions<"json"> & { silent?: boolean },
): Promise<T> {
  const { silent, ...fetchOptions } = options ?? {};

  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    return await ofetch<T>(url, {
      baseURL: "/api",
      ...fetchOptions,
      headers,
    });
  } catch (error) {
    // Abort errors should propagate silently without toast
    const isAbort =
      (error instanceof DOMException && error.name === "AbortError") ||
      (error instanceof FetchError && fetchOptions.signal?.aborted);
    if (isAbort) {
      throw error;
    }

    const detail =
      error instanceof FetchError
        ? (error.data?.detail ?? error.statusMessage ?? "Request failed")
        : error instanceof Error
          ? error.message
          : "Request failed";
    const status =
      error instanceof FetchError ? (error.status ?? 500) : 500;

    // 401: clear auth and redirect to login
    if (status === 401) {
      useAuthStore.getState().clearAuth();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }

    const apiError = new ApiError(status, detail);
    if (!silent) {
      toast.error(apiError.detail);
    }
    throw apiError;
  }
}
