export const AI_SETTINGS_STORAGE_KEY = "fixrate_ai_settings";
export const AI_SESSION_KEY = "fixrate_ai_session_key";
let memoryKey = "";

export function readAiKey(): string {
  try { return window.sessionStorage.getItem(AI_SESSION_KEY) ?? memoryKey; } catch { return memoryKey; }
}

export function writeAiKey(value: string): void {
  memoryKey = value;
  try {
    if (value) window.sessionStorage.setItem(AI_SESSION_KEY, value);
    else window.sessionStorage.removeItem(AI_SESSION_KEY);
  } catch { /* The key remains in memory for the current page. */ }
}

/** Clear secrets at an account boundary, including credentials saved by older versions. */
export function clearAiKey(): void {
  writeAiKey("");
  try {
    const raw = window.localStorage.getItem(AI_SETTINGS_STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved && typeof saved === "object" && "apiKey" in saved) {
      delete saved.apiKey;
      window.localStorage.setItem(AI_SETTINGS_STORAGE_KEY, JSON.stringify(saved));
    }
  } catch { /* Unavailable or malformed preferences never block sign-out. */ }
}
