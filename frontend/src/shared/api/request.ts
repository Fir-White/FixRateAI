export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const csrf = document.cookie.split("; ").find(item => item.startsWith("fixrate_csrf="))?.split("=")[1];
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch(url, {...options, headers, credentials: "same-origin"});
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Ошибка API (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
