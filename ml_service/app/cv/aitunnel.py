"""Cloud vision, reusing the same image checks and conservative visual guardrails."""
from .local_vision import LocalVisionClient, ProviderFailure, review_vision_photos
from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure

PROMPT_VERSION = "maintenance-aitunnel-vision-v3"
LIMITATIONS = [
    "Фото переданы облачной модели через AI Tunnel; возможны ошибки визуального описания.",
    "Фото не подтверждают скрытые операции, метрологическую точность, герметичность и безопасность оборудования.",
    "Облачная модель не принимает работу: решение и дополнительные проверки выполняет инженер.",
]
UNAVAILABLE = {"AITUNNEL_NOT_CONFIGURED", "AITUNNEL_AUTH_FAILED", "AITUNNEL_QUOTA_EXCEEDED",
               "AITUNNEL_RATE_LIMITED", "AITUNNEL_MODEL_UNAVAILABLE", "AITUNNEL_UNAVAILABLE"}


class AITunnelVisionClient(AITunnelClient):
    # The grounded three-step assessment uses self.chat; no local transport is invoked.
    assess = LocalVisionClient.assess

    def check_model(self):
        if not self.config.api_key:
            raise ProviderFailure("AITUNNEL_NOT_CONFIGURED")

    def chat(self, messages, schema, tokens):
        try:
            return super().chat(messages, schema, max(800, tokens))
        except AITunnelFailure as exc:
            # One bounded schema repair per entire photo pair. Never retry HTTP,
            # refusal, truncation, model mismatch or invalid field values.
            diagnostics = self.response_diagnostics[-1] if self.response_diagnostics else {}
            issues = diagnostics.get("validation_errors", [])
            missing_only = (bool(issues) and any(issue["type"] == "missing" for issue in issues)
                            and all(issue["type"] in ("missing", "extra_forbidden") for issue in issues))
            if str(exc) == "AITUNNEL_INVALID_RESPONSE" and missing_only and not getattr(self, "schema_repair_used", False):
                self.schema_repair_used = True
                diagnostics["repair_requested"] = True
                feedback = {"role": "user", "content":
                    "Предыдущий ответ не прошёл проверку JSON-схемы: пропущены обязательные поля. "
                    "Заново оцени те же исходные данные и верни полный JSON-объект со ВСЕМИ полями схемы. "
                    "Используй точные имена полей схемы без перевода. Для пустого списка явно используй []. "
                    "Не дополняй неизвестное выдуманными фактами."}
                try:
                    return super().chat([*messages, feedback], schema, max(800, tokens))
                except AITunnelFailure as retry_failure:
                    raise ProviderFailure(str(retry_failure)) from None
            raise ProviderFailure(str(exc)) from None


def review_cloud_photos(request, photo_loader, *, config=None, client=None, **kwargs):
    config = config or AITunnelConfig.from_environment("vision")
    client = client or AITunnelVisionClient(config)
    result = review_vision_photos(request, photo_loader, config=config, client=client,
        limitations=LIMITATIONS, failure_code="AITUNNEL_FAILED", unavailable_codes=UNAVAILABLE, **kwargs)
    if getattr(client, "schema_repair_used", False):
        result = result.model_copy(update={"limitations": [*result.limitations,
            "Первый ответ модели нарушил JSON-контракт. Выполнен один повтор в пределах общего таймаута; ошибочный ответ не использован."]})
    if client.response_model:
        result = result.model_copy(update={"limitations": [*result.limitations,
            "Модель в ответе провайдера: " + client.response_model]})
    return result
