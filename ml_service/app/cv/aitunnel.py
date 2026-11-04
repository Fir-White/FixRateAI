"""Cloud vision, reusing the same image checks and conservative visual guardrails."""
from .local_vision import LocalVisionClient, ProviderFailure, review_vision_photos
from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure

PROMPT_VERSION = "maintenance-aitunnel-vision-v1"
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
            raise ProviderFailure(str(exc)) from None


def review_cloud_photos(request, photo_loader, *, config=None, client=None, **kwargs):
    config = config or AITunnelConfig.from_environment("vision")
    client = client or AITunnelVisionClient(config)
    result = review_vision_photos(request, photo_loader, config=config, client=client,
        limitations=LIMITATIONS, failure_code="AITUNNEL_FAILED", unavailable_codes=UNAVAILABLE, **kwargs)
    if client.response_model:
        result = result.model_copy(update={"limitations": [*result.limitations,
            "Модель в ответе провайдера: " + client.response_model]})
    return result
