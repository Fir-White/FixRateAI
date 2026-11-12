import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AiModelSelector } from "@/features/ai/AiModelSelector";
import {
  getStoredAiSettings,
  saveStoredAiSettings,
} from "@/features/ai/aiSettings";
import { maintenanceApi } from "@/shared/api/maintenance";
import { AI_SESSION_KEY, clearAiKey } from "@/shared/lib/aiCredentials";

vi.mock("@/shared/api/maintenance", () => ({
  maintenanceApi: {
    getAiModels: vi.fn(),
    photoReview: vi.fn(),
  },
}));

describe("AiModelSelector and aiSettings", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    clearAiKey();
    vi.clearAllMocks();
  });

  it("keeps the model preference across tabs while the personal key stays in this session", () => {
    expect(getStoredAiSettings()).toEqual({
      provider: "clip",
      model: "",
      apiKey: "",
    });

    saveStoredAiSettings({
      provider: "ollama",
      model: "qwen3.5:4b",
      apiKey: "test-key",
    });

    expect(getStoredAiSettings()).toEqual({
      provider: "ollama",
      model: "qwen3.5:4b",
      apiKey: "test-key",
    });
    expect(window.localStorage.getItem("fixrate_ai_settings")).not.toContain("test-key");
    expect(window.sessionStorage.getItem(AI_SESSION_KEY)).toBe("test-key");
    clearAiKey();
    expect(getStoredAiSettings()).toEqual({ provider: "ollama", model: "qwen3.5:4b", apiKey: "" });
  });

  it("migrates an old key out of persistent storage without losing the current session", () => {
    window.localStorage.setItem("fixrate_ai_settings", JSON.stringify({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "old-key" }));
    expect(getStoredAiSettings()).toEqual({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "old-key" });
    expect(window.localStorage.getItem("fixrate_ai_settings")).not.toContain("old-key");
    expect(window.sessionStorage.getItem(AI_SESSION_KEY)).toBe("old-key");
    clearAiKey();
    expect(getStoredAiSettings().apiKey).toBe("");
  });

  it("removes an unmigrated legacy key at an account boundary", () => {
    window.localStorage.setItem("fixrate_ai_settings", JSON.stringify({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "old-key" }));
    clearAiKey();
    expect(window.localStorage.getItem("fixrate_ai_settings")).not.toContain("old-key");
    expect(getStoredAiSettings()).toEqual({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "" });
  });

  it("retains the selection and key in memory when browser storage is unavailable", () => {
    const events = vi.fn();
    window.addEventListener("fixrate:ai-settings-changed", events);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    try {
      saveStoredAiSettings({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "memory-only" });
      expect(getStoredAiSettings()).toEqual({ provider: "aitunnel", model: "qwen3.7-flash", apiKey: "memory-only" });
      expect(events).toHaveBeenCalledOnce();
    } finally {
      vi.restoreAllMocks();
      window.removeEventListener("fixrate:ai-settings-changed", events);
      clearAiKey();
    }
  });

  it("renders compact mode and allows switching providers", async () => {
    vi.mocked(maintenanceApi.getAiModels).mockResolvedValueOnce({
      current_provider: "clip",
      providers: [
        {
          id: "clip",
          name: "Встроенный CLIP (CPU)",
          description: "Локальный классификатор",
          available: true,
          models: [{ id: "openai/clip-vit-base-patch32", name: "CLIP ViT-B/32" }],
        },
        {
          id: "ollama",
          name: "Локальная Ollama",
          description: "Локальная служба",
          available: true,
          models: [
            { id: "qwen3.5:4b", name: "qwen3.5:4b", size: 2500000000 },
            { id: "llava:13b", name: "llava:13b", size: 7500000000 },
          ],
        },
        {
          id: "aitunnel",
          name: "Облачный AI Tunnel",
          description: "Облако",
          available: true,
          has_server_key: true,
          models: [
            { id: "qwen3.7-flash", name: "Qwen3.7 Flash" },
            { id: "qwen2.5-vl-72b-instruct", name: "Qwen2.5-VL" },
          ],
        },
      ],
    });

    render(<AiModelSelector variant="compact" />);

    // Initially on CLIP
    expect(screen.getByText(/CLIP \(CPU\)/)).toBeInTheDocument();
    expect(screen.getByText(/Быстрая встроенная модель CLIP/)).toBeInTheDocument();

    // Switch to Ollama
    fireEvent.click(screen.getByText(/Ollama \(Локально\)/));

    await waitFor(() => {
      expect(screen.getByText(/Ollama активна/)).toBeInTheDocument();
    });

    expect(getStoredAiSettings().provider).toBe("ollama");

    // Switch to AI Tunnel
    fireEvent.click(screen.getByText(/AI Tunnel \(Облако\)/));
    expect(getStoredAiSettings().provider).toBe("aitunnel");
  });

  it("renders card mode and handles re-scan and api key updates", async () => {
    vi.mocked(maintenanceApi.getAiModels).mockResolvedValue({
      current_provider: "aitunnel",
      providers: [
        {
          id: "clip",
          name: "CLIP",
          description: "CLIP",
          available: true,
          models: [],
        },
        {
          id: "ollama",
          name: "Ollama",
          description: "Ollama",
          available: false,
          models: [],
        },
        {
          id: "aitunnel",
          name: "AI Tunnel",
          description: "AI Tunnel",
          available: true,
          has_server_key: false,
          models: [
            { id: "qwen3.7-flash", name: "Qwen3.7 Flash" },
          ],
        },
      ],
    });

    saveStoredAiSettings({
      provider: "aitunnel",
      model: "qwen3.7-flash",
      apiKey: "",
    });

    render(<AiModelSelector variant="card" />);

    await waitFor(() => {
      expect(screen.getByLabelText("Персональный API-ключ")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Персональный API-ключ"), {
      target: { value: "sk-my-cloud-key" },
    });

    expect(getStoredAiSettings().apiKey).toBe("sk-my-cloud-key");
  });
});
