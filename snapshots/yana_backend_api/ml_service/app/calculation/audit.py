"""Аудит сметных расчётов и верификация согласованности единиц измерения."""
from decimal import Decimal
from typing import NamedTuple
from app.schemas.response import EstimateItemDTO


class AuditCheckResult(NamedTuple):
    """Результат проверки сметной позиции."""
    is_valid: bool
    warnings: list[str]
    errors: list[str]


class EstimateAuditor:
    """Аудитор сметных расчётов."""

    @staticmethod
    def audit_item(item: EstimateItemDTO) -> AuditCheckResult:
        warnings: list[str] = []
        errors: list[str] = []

        if item.quantity <= Decimal("0"):
            errors.append(f"Количество по позиции '{item.rate_code}' должно быть строго положительным, получено {item.quantity}")

        if item.base_price < Decimal("0"):
            errors.append(f"Базовая цена позиции '{item.rate_code}' не может быть отрицательной, получено {item.base_price}")

        if item.line_total < Decimal("0"):
            errors.append(f"Итоговая сумма позиции '{item.rate_code}' не может быть отрицательной")

        # Проверка аномально больших объёмов (аудиторское предупреждение)
        if item.unit in ("m2", "m3") and item.quantity > Decimal("5000"):
            warnings.append(f"Внимание: аномально большой объём работ ({item.quantity} {item.unit}) по позиции {item.rate_code}")

        if item.unit == "pcs" and item.quantity > Decimal("1000"):
            warnings.append(f"Внимание: аномально большое количество элементов ({item.quantity} шт) по позиции {item.rate_code}")

        return AuditCheckResult(
            is_valid=len(errors) == 0,
            warnings=warnings,
            errors=errors,
        )
