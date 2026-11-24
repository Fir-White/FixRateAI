import { useState, useEffect, useCallback } from "react";
import {
  maintenanceApi,
  type AiProvider,
  type AiModelsResponse,
} from "@/shared/api/maintenance";
import { AI_SETTINGS_STORAGE_KEY, readAiKey, writeAiKey } from "@/shared/lib/aiCredentials";

export { AI_SETTINGS_STORAGE_KEY } from "@/shared/lib/aiCredentials";
export const AI_SETTINGS_CHANGE_EVENT = "fixrate:ai-settings-changed";

export interface AiSettings {
  provider: AiProvider;
  model: string;
  apiKey: string;
}

export const DEFAULT_AI_SETTINGS: AiSettings = {
  provider: "clip",
  model: "",
  apiKey: "",
};
let memoryPreferences: Pick<AiSettings, "provider" | "model"> | undefined;

export function getPhotoReviewOptions(): AiSettings | undefined {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage?.getItem(AI_SETTINGS_STORAGE_KEY) : null;
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.apiKey === "string") {
        if (!readAiKey()) writeAiKey(parsed.apiKey);
        delete parsed.apiKey;
        window.localStorage.setItem(AI_SETTINGS_STORAGE_KEY, JSON.stringify(parsed));
      }
      const validProviders: AiProvider[] = ["clip", "ollama", "aitunnel"];
      if (validProviders.includes(parsed?.provider)) {
        memoryPreferences = { provider: parsed.provider, model: typeof parsed?.model === "string" ? parsed.model : "" };
      }
    }
  } catch {
    // Preserve an explicit preference if the browser blocks storage.
  }
  return memoryPreferences && { ...memoryPreferences, apiKey: readAiKey() };
}

export function getStoredAiSettings(): AiSettings {
  return getPhotoReviewOptions() ?? { ...DEFAULT_AI_SETTINGS, apiKey: readAiKey() };
}

export function saveStoredAiSettings(settings: AiSettings): void {
  memoryPreferences = { provider: settings.provider, model: settings.model };
  writeAiKey(settings.apiKey);
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(AI_SETTINGS_STORAGE_KEY, JSON.stringify({ provider: settings.provider, model: settings.model }));
    }
  } catch {
    // Ignore storage quota or disabled errors
  }
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(AI_SETTINGS_CHANGE_EVENT, { detail: settings }));
}

export function useAiSettings(autoFetch = true) {
  const [settings, setSettingsState] = useState<AiSettings>(getStoredAiSettings);
  const [modelsData, setModelsData] = useState<AiModelsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setSettings = useCallback((newSettings: AiSettings | ((prev: AiSettings) => AiSettings)) => {
    setSettingsState(prev => {
      const next = typeof newSettings === "function" ? newSettings(prev) : newSettings;
      saveStoredAiSettings(next);
      return next;
    });
  }, []);

  const updateSetting = useCallback(<K extends keyof AiSettings>(key: K, value: AiSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  }, [setSettings]);

  const fetchModels = useCallback(async (isRescan = false) => {
    if (isRescan) setScanning(true);
    else setLoading(true);
    setError(null);
    try {
      const resp = await maintenanceApi.getAiModels();
      if (resp && Array.isArray(resp.providers)) {
        setModelsData(resp);
        const stored = getPhotoReviewOptions();
        const defaultProvider = resp.providers.find(item => item.id === resp.current_provider)?.id ?? DEFAULT_AI_SETTINGS.provider;
        const provider = stored?.provider ?? defaultProvider;
        const models = resp.providers.find(item => item.id === provider)?.models ?? [];
        const selected = models.find(item => item.id === stored?.model);
        const settings = { provider, model: selected?.id ?? models[0]?.id ?? "", apiKey: readAiKey() };
        if (stored && settings.model && !selected) saveStoredAiSettings(settings);
        setSettingsState(settings);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось получить список моделей");
    } finally {
      setLoading(false);
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    const handleSettingsChange = (e: Event) => {
      const customEvent = e as CustomEvent<AiSettings>;
      if (customEvent.detail) {
        setSettingsState(customEvent.detail);
      } else {
        setSettingsState(getStoredAiSettings());
      }
    };
    window.addEventListener(AI_SETTINGS_CHANGE_EVENT, handleSettingsChange);
    window.addEventListener("storage", handleSettingsChange);
    return () => {
      window.removeEventListener(AI_SETTINGS_CHANGE_EVENT, handleSettingsChange);
      window.removeEventListener("storage", handleSettingsChange);
    };
  }, []);

  useEffect(() => {
    if (autoFetch) {
      void fetchModels(false);
    }
  }, [autoFetch, fetchModels]);

  return {
    settings,
    setSettings,
    updateSetting,
    modelsData,
    loading,
    scanning,
    error,
    refreshModels: () => fetchModels(true),
  };
}
