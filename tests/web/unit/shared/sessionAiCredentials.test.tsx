import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { SessionProvider, useSession } from "@/shared/session/SessionContext";
import { AI_SESSION_KEY, writeAiKey } from "@/shared/lib/aiCredentials";
import { request } from "@/shared/api/request";

vi.mock("@/shared/api/request", () => ({
  DEMO_MODE: false,
  ApiError: class extends Error { status = 401; },
  request: vi.fn(),
}));

it("clears a personal AI key when the authenticated user signs out", async () => {
  vi.mocked(request).mockImplementation(async url => url.endsWith("/session")
    ? { profile: { userId: "one", role: "engineer", siteId: "site", name: "QA", timezone: "UTC" } } as never
    : undefined as never);
  writeAiKey("session-key");
  window.localStorage.setItem("fixrate_ai_settings", JSON.stringify({ provider: "aitunnel", model: "model", apiKey: "legacy-key" }));
  function Probe() {
    const { profile, logout } = useSession();
    return profile ? <button onClick={() => void logout()}>Выйти</button> : <span>Нет сессии</span>;
  }
  render(<SessionProvider><Probe /></SessionProvider>);
  await userEvent.setup().click(await screen.findByRole("button", { name: "Выйти" }));
  await waitFor(() => expect(screen.getByText("Нет сессии")).toBeInTheDocument());
  expect(window.sessionStorage.getItem(AI_SESSION_KEY)).toBeNull();
  expect(window.localStorage.getItem("fixrate_ai_settings")).not.toContain("legacy-key");
});
