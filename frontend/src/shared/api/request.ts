import { invalidateApiQueries } from "@/shared/lib/apiQueryCache";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly details?: unknown, public readonly code?: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const csrf = document.cookie.split("; ").find(item => item.startsWith("fixrate_csrf="))?.split("=")[1];
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch(url, {...options, headers, credentials: "same-origin"});
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) invalidateApiQueries();
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, typeof payload?.detail === "string" ? payload.detail : `Ошибка API (${response.status})`, payload?.error?.details ?? payload?.detail, payload?.error?.code);
  }
  if (!["GET", "HEAD", "OPTIONS"].includes((options.method ?? "GET").toUpperCase())) invalidateApiQueries();
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
