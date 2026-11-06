import { useState, useEffect, useCallback } from "react";
import {
  maintenanceApi,
  type AiProvider,
  type AiModelsResponse,
} from "@/shared/api/maintenance";

export const AI_SETTINGS_STORAGE_KEY = "fixrate_ai_settings";
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

export function getStoredAiSettings(): AiSettings {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage?.getItem(AI_SETTINGS_STORAGE_KEY) : null;
    if (!raw) return DEFAULT_AI_SETTINGS;
    const parsed = JSON.parse(raw);
    const validProviders: AiProvider[] = ["clip", "ollama", "aitunnel"];
    const provider: AiProvider = validProviders.includes(parsed?.provider) ? parsed.provider : "clip";
    return {
      provider,
      model: typeof parsed?.model === "string" ? parsed.model : "",
      apiKey: typeof parsed?.apiKey === "string" ? parsed.apiKey : "",
    };
  } catch {
    return DEFAULT_AI_SETTINGS;
  }
}

export function saveStoredAiSettings(settings: AiSettings): void {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(AI_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
      window.dispatchEvent(new CustomEvent(AI_SETTINGS_CHANGE_EVENT, { detail: settings }));
    }
  } catch {
    // Ignore storage quota or disabled errors
  }
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
        // If current model is not set or doesn't belong to the active provider, set smart default
        setSettingsState(curr => {
          const providerInfo = resp.providers.find(p => p.id === curr.provider);
          if (providerInfo && providerInfo.models.length > 0) {
            const existsInProvider = providerInfo.models.some(m => m.id === curr.model);
            if (!curr.model || !existsInProvider) {
              const defaultModel = providerInfo.models[0].id;
              const updated = { ...curr, model: defaultModel };
              saveStoredAiSettings(updated);
              return updated;
            }
          }
          return curr;
        });
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
