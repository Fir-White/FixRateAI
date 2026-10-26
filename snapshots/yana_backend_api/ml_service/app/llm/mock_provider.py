"""Mock-провайдер LLM с детерминированным эвристическим разбором текста."""
from decimal import Decimal
import re
from typing import TypeVar
from pydantic import BaseModel

from app.llm.schemas import NormalizedDefectDescription

T = TypeVar("T", bound=BaseModel)

# Регулярные выражения для извлечения физических параметров из русского текста
RE_LENGTH = re.compile(r"(?:длин[а-я]*|протяжённост[а-я]*)\s*(?:составляет|:|-)?\s*(\d+(?:[.,]\d+)?)\s*(?:м|метр[а-я]*)", re.I)
RE_DIRECT_M = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:м(?![\d2²])|метр[а-я]*)\s*(?:в длину|длиной)?",
    re.I,
)
RE_COUNT = re.compile(r"(\d+)\s*(?:шт|штук[а-я]*|плит[а-я]*)", re.I)
RE_AREA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:м2|кв\.?\s*м|квадратн[а-я]*\s*метр[а-я]*)", re.I)


class MockLLMProvider:
    """Mock-провайдер LLM, извлекающий атрибуты дефектов эвристическим анализом."""

    def complete_structured(self, prompt: str, schema_cls: type[T]) -> T:
        if schema_cls != NormalizedDefectDescription:
            return schema_cls()

        text_lower = prompt.lower()
        defect_type = None
        materials: list[str] = []
        measurements: dict[str, Decimal] = {}
        location = None

        # Определение типа дефекта
        if "трещин" in text_lower or "расщелин" in text_lower:
            defect_type = "facade_crack"
        elif "плитк" in text_lower or "скол" in text_lower:
            defect_type = "tile_chip"
        elif "протеч" in text_lower or "затопл" in text_lower or "сырост" in text_lower or "паркинг" in text_lower:
            defect_type = "parking_leak"

        # Извлечение материалов
        if "кирпич" in text_lower:
            materials.append("кирпич")
        if "бетон" in text_lower:
            materials.append("бетон")
        if "штукатурк" in text_lower or "оштукатур" in text_lower:
            materials.append("штукатурка")
        if "керамогранит" in text_lower:
            materials.append("керамогранит")
        if "плитк" in text_lower:
            materials.append("плитка")

        # Извлечение длины
        m_len = RE_LENGTH.search(prompt) or RE_DIRECT_M.search(prompt)
        if m_len:
            val_str = m_len.group(1).replace(",", ".")
            measurements["length_m"] = Decimal(val_str)

        # Извлечение количества
        m_cnt = RE_COUNT.search(prompt)
        if m_cnt:
            measurements["count"] = Decimal(m_cnt.group(1))

        # Извлечение площади
        m_area = RE_AREA.search(prompt)
        if m_area:
            val_str = m_area.group(1).replace(",", ".")
            measurements["area_m2"] = Decimal(val_str)

        # Локализация
        if "фасад" in text_lower or "стен" in text_lower:
            location = "наружная стена фасада"
        elif "крыльц" in text_lower or "вход" in text_lower:
            location = "крыльцо входной группы"
        elif "паркинг" in text_lower or "подземн" in text_lower:
            location = "подземный паркинг"

        return NormalizedDefectDescription(
            detected_defect_type=defect_type,
            defect_description=prompt.strip(),
            location_details=location,
            materials=materials,
            extracted_measurements=measurements,
            unclear_aspects=[],
        )
