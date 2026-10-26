"""Провайдер интеграции с GigaChat (Сбер) для структурированного анализа дефектов."""
import json
import logging
import re
from typing import Any, TypeVar
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.protocol import LLMProviderProtocol

logger = logging.getLogger("app.llm.gigachat")
T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = """Ты — эксперт по обследованию строительных конструкций и инженер-сметчик FixRate AI.
Твоя задача — проанализировать описание повреждения здания и извлечь структурированные факты.

Допустимые коды типов дефектов (detected_defect_type):
- "facade_crack" — трещина на штукатурном, кирпичном, блочном или панельном фасаде
- "tile_chip" — скол, повреждение или разрушение облицовочной плитки/керамогранита
- "parking_leak" — протечка, подтопление, следы сырости в подземном паркинге или подвале
- null — если дефект не относится к указанным выше

Правила извлечения физических параметров (extracted_measurements):
- Переводи все размеры в базовые единицы СИ:
  * длина -> "length_m" (метры)
  * ширина/раскрытие -> "width_m" (метры, например 2 мм -> 0.002, 10 см -> 0.10)
  * глубина -> "depth_m" (метры)
  * площадь -> "area_m2" (кв. метры)
  * количество повреждённых элементов -> "count" (штуки, число)

СТРОГИЙ ЗАПРЕТ:
Ни при каких обстоятельствах не придумывай цены, расценки, стоимость материалов или валюту. Финансовые поля отсутствуют в схеме и запрещены.

Формат JSON строго следующий:
{
  "detected_defect_type": "facade_crack",
  "defect_description": "Краткое описание повреждения",
  "location_details": "Локализация (например, наружная стена)",
  "materials": ["штукатурка"],
  "extracted_measurements": {
    "length_m": 4.5,
    "width_m": 0.002
  },
  "unclear_aspects": []
}

Верни ответ СТРОГО в виде JSON-объекта. Никакого дополнительного текста до или после JSON.
"""


class GigaChatProvider(LLMProviderProtocol):
    """Реализация LLMProviderProtocol поверх официального SDK GigaChat."""

    def __init__(
        self,
        credentials: str | None = None,
        scope: str | None = None,
        model: str | None = None,
        verify_ssl_certs: bool | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.credentials = credentials if credentials is not None else settings.gigachat_credentials
        self.scope = scope or settings.gigachat_scope
        self.model = model or settings.gigachat_model
        self.verify_ssl_certs = (
            verify_ssl_certs if verify_ssl_certs is not None else settings.gigachat_verify_ssl_certs
        )
        self.timeout = timeout if timeout is not None else settings.gigachat_timeout

        self._client: Any = None

    def _get_client(self) -> Any:
        """Ленивая инициализация клиента GigaChat."""
        if self._client is None:
            if not self.credentials:
                raise ValueError("GigaChat credentials не настроены. Укажите ML_GIGACHAT_CREDENTIALS в .env")

            try:
                from gigachat import GigaChat
            except ImportError as e:
                raise ImportError(
                    "Пакет 'gigachat' не установлен в окружении. Установите: pip install gigachat"
                ) from e

            self._client = GigaChat(
                credentials=self.credentials,
                scope=self.scope,
                model=self.model,
                verify_ssl_certs=self.verify_ssl_certs,
                timeout=self.timeout,
            )
        return self._client

    def complete_structured(self, prompt: str, schema_cls: type[T]) -> T:
        """Отправляет запрос в GigaChat и парсит результат в Pydantic-модель."""
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,  # Низкая температура для максимальной детерминированности
        }

        from gigachat.models import ChatCompletion

        response = client.chat(payload)
        content = ""
        if isinstance(response, ChatCompletion) and response.choices:
            content = response.choices[0].message.content or ""
        elif hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content or ""
        else:
            raise RuntimeError(f"Неожиданный формат ответа GigaChat: {response}")

        logger.debug("Сырой ответ GigaChat: %s", content)

        # Очищаем markdown-блоки ```json ... ``` если модель их добавила
        json_str = self._extract_json_string(content)
        data = json.loads(json_str)

        # Нормализация: если легковесная модель вынесла параметры на верхний уровень
        if isinstance(data, dict):
            measurements = data.setdefault("extracted_measurements", {})
            for param in ["length_m", "width_m", "depth_m", "area_m2", "count"]:
                if param in data and param not in measurements:
                    measurements[param] = data.pop(param)

        return schema_cls.model_validate(data)

    @staticmethod
    def _extract_json_string(text: str) -> str:
        """Извлекает валидную JSON-строку из текста модели."""
        text = text.strip()
        # Поиск блока ```json ... ```
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()

        # Поиск первой открывающей { и последней закрывающей }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()

        return text
