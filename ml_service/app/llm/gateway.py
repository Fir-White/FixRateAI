"""Фасад Model Gateway для работы с языковыми моделями."""
import logging
from app.core.config import get_settings
from app.llm.mock_provider import MockLLMProvider
from app.llm.protocol import LLMProviderProtocol
from app.llm.schemas import NormalizedDefectDescription

logger = logging.getLogger("app.llm.gateway")


class LLMGateway:
    """Шлюз вызова языковых моделей с валидацией схем и защитой от галлюцинаций."""

    def __init__(self, provider: LLMProviderProtocol | None = None) -> None:
        settings = get_settings()
        if provider is not None:
            self.provider = provider
        elif settings.llm_provider == "mock" or not settings.llm_api_key:
            self.provider = MockLLMProvider()
        else:
            # Fallback на mock при отсутствии внешнего провайдера
            self.provider = MockLLMProvider()

    def normalize_user_text(self, text: str) -> NormalizedDefectDescription:
        """Преобразует пользовательский текст в валидированную структуру дефекта."""
        if not text or not text.strip():
            return NormalizedDefectDescription(defect_description="")

        prompt = (
            "Проанализируй описание повреждения объекта недвижимости. "
            "Извлеки тип дефекта, материалы и числовые физические измерения. "
            "Категорически не придумывай цены и расценки.\n\n"
            f"Описание: {text}"
        )

        try:
            result = self.provider.complete_structured(prompt, NormalizedDefectDescription)
            return result
        except Exception as e:
            logger.error("Ошибка при вызове LLM провайдера: %s, переключение на эвристический fallback", e)
            fallback = MockLLMProvider()
            return fallback.complete_structured(prompt, NormalizedDefectDescription)
