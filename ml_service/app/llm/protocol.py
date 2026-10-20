"""Протокол взаимодействия с языковыми моделями (LLM)."""
from typing import Protocol, TypeVar, runtime_checkable
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Интерфейс провайдера языковой модели для структурированного вывода."""

    def complete_structured(self, prompt: str, schema_cls: type[T]) -> T:
        """Отправляет промпт в LLM и возвращает строго валидированный Pydantic-объект."""
        ...
