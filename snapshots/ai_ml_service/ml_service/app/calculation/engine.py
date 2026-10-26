"""Детерминированный расчётный движок FixRate AI.

Выполняет расчёт объёмов работ по дефектам, вычисление стоимости каждой сметной позиции
и итоговой сметной суммы строго с использованием финансовой арифметики Decimal.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from app.calculation.formulas import (
    calculate_crack_repair_area,
    calculate_crack_linear,
    calculate_tile_replacement_area,
    calculate_parking_waterproofing_area,
    FormulaResult,
)
from app.schemas.response import EstimateItemDTO

CURRENCY_ROUNDING = Decimal("0.01")
VOLUME_ROUNDING = Decimal("0.0001")


class CalculationEngine:
    """Движок расчёта сметных позиций и объёмов."""

    @staticmethod
    def calculate_work_quantity(defect_type: str, measurements: dict[str, Any]) -> FormulaResult:
        """Подбирает формулу и рассчитывает объём работ по дефекту и его измерениям."""
        d_type = defect_type.lower()

        if d_type == "facade_crack":
            # Ищем длину
            length = measurements.get("length_m") or measurements.get("length")
            if length is None:
                raise ValueError("Для расчёта трещины фасада требуется измерение длины ('length_m')")
            len_dec = Decimal(str(length))
            
            # Опциональная ширина разделки
            width = measurements.get("width_m") or measurements.get("width")
            w_dec = Decimal(str(width)) if width is not None else None
            return calculate_crack_repair_area(length_m=len_dec, width_m=w_dec)

        elif d_type == "tile_chip":
            count = measurements.get("count") or measurements.get("damaged_tiles_count")
            direct_area = measurements.get("area_m2") or measurements.get("area")
            
            c_int = int(count) if count is not None else None
            a_dec = Decimal(str(direct_area)) if direct_area is not None else None
            
            tile_area = measurements.get("tile_area_m2")
            t_dec = Decimal(str(tile_area)) if tile_area is not None else None
            return calculate_tile_replacement_area(
                damaged_tiles_count=c_int,
                tile_area_m2=t_dec,
                direct_area_m2=a_dec,
            )

        elif d_type == "parking_leak":
            direct_area = measurements.get("area_m2") or measurements.get("area") or measurements.get("leak_area_m2")
            if direct_area is not None:
                return calculate_parking_waterproofing_area(leak_area_m2=Decimal(str(direct_area)))
            
            length = measurements.get("length_m") or measurements.get("length")
            width = measurements.get("width_m") or measurements.get("width")
            if length is not None and width is not None:
                return calculate_parking_waterproofing_area(length_m=Decimal(str(length)), width_m=Decimal(str(width)))
            
            raise ValueError("Для расчёта гидроизоляции парковки требуется 'area_m2' либо ('length_m' и 'width_m')")

        else:
            # Универсальный fallback, если уже передано вычисленное количество
            qty = measurements.get("quantity") or measurements.get("area_m2") or measurements.get("length_m")
            if qty is not None:
                q_dec = Decimal(str(qty)).quantize(VOLUME_ROUNDING, rounding=ROUND_HALF_UP)
                unit = measurements.get("unit", "m2")
                return FormulaResult(
                    quantity=q_dec,
                    unit=unit,
                    formula_id="FORMULA_DIRECT_QUANTITY_V1",
                    description="Прямое применение переданного количества",
                    trace=f"Q = {q_dec} {unit}",
                )
            raise ValueError(f"Неизвестный тип дефекта '{defect_type}' или отсутствуют необходимые измерения")

    @classmethod
    def create_estimate_item(
        cls,
        rate_code: str,
        work_name: str,
        quantity: Decimal,
        unit: str,
        base_price: Decimal,
        source_ref: str,
        formula_id: str | None = None,
        quantity_trace: str | None = None,
        unit_multiplier: Decimal = Decimal("1"),
    ) -> EstimateItemDTO:
        """Создаёт позицию сметы с расчётом стоимости и сохранением трассировки."""
        line_total = (quantity * base_price * unit_multiplier).quantize(CURRENCY_ROUNDING, rounding=ROUND_HALF_UP)
        trace_steps = []
        if quantity_trace:
            trace_steps.append(f"Объём: {quantity_trace}")
        
        calc_str = f"Итог: {quantity} {unit} * {base_price} RUB"
        if unit_multiplier != Decimal("1"):
            calc_str += f" * коэфф.{unit_multiplier}"
        calc_str += f" = {line_total} RUB"
        trace_steps.append(calc_str)

        return EstimateItemDTO(
            item_id=f"item-{uuid4().hex[:8]}",
            rate_code=rate_code,
            work_name=work_name,
            quantity=quantity,
            unit=unit,
            base_price=base_price,
            line_total=line_total,
            source_ref=source_ref,
            formula_id=formula_id,
            calculation_trace=trace_steps,
            warnings=[],
        )

    @staticmethod
    def calculate_total_cost(items: list[EstimateItemDTO]) -> Decimal:
        """Детерминированно суммирует позиции сметы."""
        total = sum((item.line_total for item in items), Decimal("0.00"))
        return total.quantize(CURRENCY_ROUNDING, rounding=ROUND_HALF_UP)
