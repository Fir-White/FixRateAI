import { useState } from "react";
import { useAiSettings } from "./aiSettings";
import { Button } from "@/shared/ui/Button";
import { FormField, Input, Select } from "@/shared/ui/Form";
import { FilterChip } from "@/shared/ui/FilterChip";
import { Badge } from "@/shared/ui/Badge";
import type { AiProvider } from "@/shared/api/maintenance";

interface AiModelSelectorProps {
  variant?: "compact" | "card";
  className?: string;
  autoFetch?: boolean;
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1) return ` (${gb.toFixed(1)} ГБ)`;
  const mb = bytes / (1024 * 1024);
  return ` (${Math.round(mb)} МБ)`;
}

export function AiModelSelector({
  variant = "compact",
  className = "",
  autoFetch = true,
}: AiModelSelectorProps) {
  const {
    settings,
    updateSetting,
    modelsData,
    loading,
    scanning,
    error,
    refreshModels,
  } = useAiSettings(autoFetch);

  const [showKey, setShowKey] = useState(false);
  const [saveNotice, setSaveNotice] = useState(false);

  const currentProviderInfo = modelsData?.providers?.find(
    (p) => p.id === settings.provider
  );

  const ollamaProvider = modelsData?.providers?.find((p) => p.id === "ollama");
  const aitunnelProvider = modelsData?.providers?.find((p) => p.id === "aitunnel");

  const isOllamaOnline = ollamaProvider?.available ?? false;
  const hasServerKey = aitunnelProvider?.has_server_key ?? false;

  const handleProviderSelect = (prov: AiProvider) => {
    const provInfo = modelsData?.providers?.find((p) => p.id === prov);
    const defaultModel = provInfo?.models?.[0]?.id || "";
    updateSetting("provider", prov);
    if (defaultModel && !settings.model) {
      updateSetting("model", defaultModel);
    }
    triggerSaved();
  };

  const handleModelChange = (modelId: string) => {
    updateSetting("model", modelId);
    triggerSaved();
  };

  const handleKeyChange = (key: string) => {
    updateSetting("apiKey", key);
    triggerSaved();
  };

  const triggerSaved = () => {
    setSaveNotice(true);
    setTimeout(() => setSaveNotice(false), 2000);
  };

  if (variant === "compact") {
    return (
      <div className={`space-y-3 rounded-xl border border-line bg-surface/50 p-3.5 sm:p-4 ${className}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold text-ink-soft">
            Нейросеть для анализа фото:
          </span>
          <div className="flex items-center gap-1.5">
            {saveNotice && (
              <span className="text-[11px] font-medium text-accent animate-fade-in">
                ✓ Сохранено
              </span>
            )}
            {settings.provider === "ollama" && (
              <Badge tone={isOllamaOnline ? "success" : "warning"}>
                {isOllamaOnline ? "Ollama активна" : "Ollama офлайн"}
              </Badge>
            )}
            {settings.provider === "aitunnel" && (
              <Badge tone={hasServerKey || settings.apiKey ? "info" : "warning"}>
                {settings.apiKey ? "Свой API-ключ" : hasServerKey ? "Ключ сервера" : "Нужен ключ"}
              </Badge>
            )}
          </div>
        </div>

        {/* Provider selection chips */}
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Провайдер нейросети">
          <FilterChip
            active={settings.provider === "clip"}
            onClick={() => handleProviderSelect("clip")}
          >
            ⚡ CLIP (CPU)
          </FilterChip>
          <FilterChip
            active={settings.provider === "ollama"}
            onClick={() => handleProviderSelect("ollama")}
          >
            🖥️ Ollama (Локально)
          </FilterChip>
          <FilterChip
            active={settings.provider === "aitunnel"}
            onClick={() => handleProviderSelect("aitunnel")}
          >
            ☁️ AI Tunnel (Облако)
          </FilterChip>
        </div>

        {/* Details based on selected provider */}
        {settings.provider === "clip" && (
          <p className="text-xs leading-5 text-muted">
            Быстрая встроенная модель CLIP ViT-B/32 на CPU. Базовый регламентный анализ без сторонних сервисов.
          </p>
        )}

        {settings.provider === "ollama" && (
          <div className="space-y-2 pt-1">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <Select
                  value={settings.model || ollamaProvider?.models?.[0]?.id || "qwen3.5:4b"}
                  onChange={(e) => handleModelChange(e.target.value)}
                  disabled={loading || scanning}
                  aria-label="Модель Ollama"
                >
                  {ollamaProvider?.models?.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}{formatBytes(m.size)}
                    </option>
                  )) || <option value="qwen3.5:4b">qwen3.5:4b</option>}
                </Select>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refreshModels()}
                disabled={loading || scanning}
                title="Сканировать локально установленные модели Ollama"
              >
                {scanning ? "Поиск…" : "🔄 Сканировать"}
              </Button>
            </div>

            {!isOllamaOnline && (
              <p className="text-xs leading-5 text-amber-300/90">
                Служба Ollama не обнаружена на 127.0.0.1:11434. Запустите <code>ollama serve</code> на компьютере.
              </p>
            )}
          </div>
        )}

        {settings.provider === "aitunnel" && (
          <div className="space-y-2.5 pt-1">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <Select
                  value={settings.model || aitunnelProvider?.models?.[0]?.id || "qwen3.7-flash"}
                  onChange={(e) => handleModelChange(e.target.value)}
                  aria-label="Облачная модель"
                >
                  {aitunnelProvider?.models?.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} {m.description ? `— ${m.description}` : ""}
                    </option>
                  )) || (
                    <>
                      <option value="qwen3.7-flash">Qwen3.7 Flash</option>
                      <option value="qwen2.5-vl-72b-instruct">Qwen2.5-VL 72B Instruct</option>
                    </>
                  )}
                </Select>
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted">
                <span>Персональный API-ключ AI Tunnel:</span>
                <button
                  type="button"
                  className="text-ink-soft hover:text-ink underline text-[11px]"
                  onClick={() => setShowKey(!showKey)}
                >
                  {showKey ? "Скрыть" : "Показать"}
                </button>
              </div>
              <Input
                type={showKey ? "text" : "password"}
                placeholder={hasServerKey ? "Используется общий ключ сервера (можно переопределить)" : "sk-..."}
                value={settings.apiKey}
                onChange={(e) => handleKeyChange(e.target.value)}
                autoComplete="off"
                className="text-xs h-9"
              />
            </div>
          </div>
        )}

        {error && (
          <p className="text-xs text-rose-300" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  // Card variant (for ProfilePage or dedicated settings view)
  return (
    <div className={`space-y-6 ${className}`}>
      {/* Provider Selector Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-line pb-4" role="radiogroup" aria-label="Провайдер нейросети">
        <FilterChip
          active={settings.provider === "clip"}
          onClick={() => handleProviderSelect("clip")}
        >
          ⚡ CLIP (CPU)
        </FilterChip>
        <FilterChip
          active={settings.provider === "ollama"}
          onClick={() => handleProviderSelect("ollama")}
        >
          🖥️ Локальная Ollama
        </FilterChip>
        <FilterChip
          active={settings.provider === "aitunnel"}
          onClick={() => handleProviderSelect("aitunnel")}
        >
          ☁️ Облачный AI Tunnel
        </FilterChip>
      </div>

      {/* Selected Provider Form */}
      {settings.provider === "clip" && (
        <div className="space-y-4 rounded-xl border border-line bg-surface/30 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">Встроенный классификатор CLIP</h3>
            <Badge tone="success">Доступен всегда</Badge>
          </div>
          <p className="text-xs leading-6 text-ink-soft">
            Модель <code>openai/clip-vit-base-patch32</code> работает локально на CPU без внешних вызовов и без интернета.
            Быстро оценивает соответствие фото регламенту ТО.
          </p>
        </div>
      )}

      {settings.provider === "ollama" && (
        <div className="space-y-4 rounded-xl border border-line bg-surface/30 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-ink">Локальная нейросеть (Ollama)</h3>
              <p className="text-xs text-muted">Хост: http://127.0.0.1:11434</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={isOllamaOnline ? "success" : "warning"}>
                {isOllamaOnline ? "Служба запущена" : "Служба не отвечает"}
              </Badge>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refreshModels()}
                disabled={loading || scanning}
              >
                {scanning ? "Сканирование…" : "🔄 Сканировать модели"}
              </Button>
            </div>
          </div>

          <FormField
            label="Установленная модель"
            htmlFor="ollama-model-select"
            hint={
              isOllamaOnline
                ? `Найдено локальных моделей: ${ollamaProvider?.models?.length ?? 0}`
                : "Для установки модели выполните: ollama run qwen2.5:4b"
            }
          >
            <Select
              id="ollama-model-select"
              value={settings.model || ollamaProvider?.models?.[0]?.id || "qwen3.5:4b"}
              onChange={(e) => handleModelChange(e.target.value)}
              disabled={loading || scanning}
            >
              {ollamaProvider?.models?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} {formatBytes(m.size)} {m.description ? `— ${m.description}` : ""}
                </option>
              )) || <option value="qwen3.5:4b">qwen3.5:4b (по умолчанию)</option>}
            </Select>
          </FormField>

          {!isOllamaOnline && (
            <div className="rounded-lg bg-amber-400/10 border border-amber-300/25 p-3 text-xs leading-5 text-amber-200">
              Локальный демон Ollama не отвечает. Убедитесь, что служба запущена (команда <code>ollama serve</code>) и доступна локально.
            </div>
          )}
        </div>
      )}

      {settings.provider === "aitunnel" && (
        <div className="space-y-4 rounded-xl border border-line bg-surface/30 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-ink">Облачные мультимодальные модели (AI Tunnel)</h3>
              <p className="text-xs text-muted">Провайдер api.aitunnel.ru</p>
            </div>
            <Badge tone={hasServerKey || settings.apiKey ? "success" : "warning"}>
              {settings.apiKey ? "Пользовательский ключ" : hasServerKey ? "Общий ключ сервера" : "Ключ не задан"}
            </Badge>
          </div>

          <FormField label="Модель зрения" htmlFor="aitunnel-model-select">
            <Select
              id="aitunnel-model-select"
              value={settings.model || aitunnelProvider?.models?.[0]?.id || "qwen3.7-flash"}
              onChange={(e) => handleModelChange(e.target.value)}
            >
              {aitunnelProvider?.models?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} {m.description ? `(${m.description})` : ""}
                </option>
              )) || (
                <>
                  <option value="qwen3.7-flash">Qwen3.7 Flash (быстрая мультимодальная)</option>
                  <option value="qwen2.5-vl-72b-instruct">Qwen2.5-VL 72B Instruct (детальный разбор)</option>
                  <option value="deepseek-ai/deepseek-vl2">DeepSeek-VL2</option>
                </>
              )}
            </Select>
          </FormField>

          <FormField
            label="Персональный API-ключ"
            htmlFor="aitunnel-key-input"
            hint={
              hasServerKey
                ? "Сервер имеет предустановленный ключ. Укажите свой ключ только при необходимости."
                : "Ключ формата sk-... из личного кабинета api.aitunnel.ru. Сохраняется локально в браузере."
            }
          >
            <div className="relative">
              <Input
                id="aitunnel-key-input"
                type={showKey ? "text" : "password"}
                placeholder="sk-..."
                value={settings.apiKey}
                onChange={(e) => handleKeyChange(e.target.value)}
                autoComplete="off"
                className="pr-20"
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted hover:text-ink"
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? "Скрыть" : "Показать"}
              </button>
            </div>
          </FormField>
        </div>
      )}

      {/* Persistence confirmation banner */}
      <div className="flex items-center justify-between pt-2 text-xs text-muted">
        <span>
          Текущая конфигурация: <strong>{currentProviderInfo?.name ?? settings.provider}</strong>
          {settings.model ? ` · ${settings.model}` : ""}
        </span>
        {saveNotice && (
          <span className="font-medium text-accent">✓ Настройки сохранены в браузере</span>
        )}
      </div>

      {error && (
        <p className="text-xs text-rose-300" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
