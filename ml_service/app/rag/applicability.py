"""Модуль проверки применимости найденных расценок к обнаруженному дефекту."""
from typing import NamedTuple
from app.rag.schemas import RateItem


class ApplicabilityResult(NamedTuple):
    """Результат аудита применимости расценки."""
    is_applicable: bool
    requires_review: bool
    rejection_reason: str | None
    warnings: list[str]


class ApplicabilityValidator:
    """Валидатор применимости кандидатов работ к контексту повреждения."""

    @staticmethod
    def validate_rate(rate: RateItem, defect_type: str) -> ApplicabilityResult:
        """Проверяет соответствие расценки типу обнаруженного дефекта."""
        d_type = defect_type.lower()
        allowed_defects = [d.lower() for d in rate.applicable_defects]

        if allowed_defects and d_type not in allowed_defects:
            return ApplicabilityResult(
                is_applicable=False,
                requires_review=True,
                rejection_reason=(
                    f"Расценка '{rate.rate_code}' предназначена для дефектов {allowed_defects}, "
                    f"а обнаружен дефект '{d_type}'"
                ),
                warnings=["Несовместимость расценки с типом повреждения"],
            )

        # Пилотный сценарий parking_leak требует ручной проверки причины протечки
        if d_type == "parking_leak":
            return ApplicabilityResult(
                is_applicable=True,
                requires_review=True,
                rejection_reason=None,
                warnings=[
                    "Внимание: расценка гидроизоляции подобрана по видимому признаку протечки. "
                    "Необходимо подтверждение скрытых причин сметчиком/экспертом."
                ],
            )

        return ApplicabilityResult(
            is_applicable=True,
            requires_review=False,
            rejection_reason=None,
            warnings=[],
        )
