"""Библиотека детерминированных формул строительных объёмов.

Ключевой принцип FixRate AI: все финансовые и геометрические вычисления
выполняются строго на типе Decimal с банковским округлением (ROUND_HALF_UP).
Использование float категорически запрещено.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple


class FormulaResult(NamedTuple):
    """Результат расчёта объёма по нормативной формуле."""
    quantity: Decimal
    unit: str
    formula_id: str
    description: str
    trace: str


# Нормативные константы по умолчанию
DEFAULT_CRACK_BAND_WIDTH_M = Decimal("0.10")  # Стандартная полоса разделки трещины (10 см)
DEFAULT_TILE_AREA_M2 = Decimal("0.09")        # Стандартная плитка 30x30 см = 0.09 м2
WATERPROOFING_MARGIN_FACTOR = Decimal("1.15") # Технологический нахлёст гидроизоляции (+15%)
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def calculate_crack_repair_area(
    length_m: Decimal,
    width_m: Decimal | None = None,
) -> FormulaResult:
    """Расчёт площади разделки и заделки трещины фасада.
    
    Формула: S = L * W_rep (м2).
    Если ширина раскрытия не задана или является технологической,
    применяется нормативная полоса заделки (0.1 м).
    """
    if length_m <= Decimal("0"):
        raise ValueError(f"Длина трещины должна быть строго положительной, получено: {length_m}")

    rep_width = width_m if (width_m is not None and width_m > Decimal("0")) else DEFAULT_CRACK_BAND_WIDTH_M
    area = (length_m * rep_width).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
    
    return FormulaResult(
        quantity=area,
        unit="m2",
        formula_id="FORMULA_CRACK_AREA_V1",
        description="Площадь заделки трещины (длина * полоса разделки)",
        trace=f"S = {length_m} m * {rep_width} m = {area} m2",
    )


def calculate_crack_linear(length_m: Decimal) -> FormulaResult:
    """Линейный расчёт герметизации трещины / шва в погонных метрах."""
    if length_m <= Decimal("0"):
        raise ValueError(f"Длина трещины должна быть строго положительной, получено: {length_m}")

    qty = length_m.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
    return FormulaResult(
        quantity=qty,
        unit="m",
        formula_id="FORMULA_CRACK_LINEAR_V1",
        description="Линейная длина герметизации шва/трещины",
        trace=f"L = {qty} m",
    )


def calculate_tile_replacement_area(
    damaged_tiles_count: int | None = None,
    tile_area_m2: Decimal | None = None,
    direct_area_m2: Decimal | None = None,
) -> FormulaResult:
    """Расчёт площади замены облицовочной плитки.
    
    Формула:
    - Если задана прямая площадь: S = direct_area_m2.
    - Если задано количество плиток: S = N * S_one_tile.
    """
    if direct_area_m2 is not None and direct_area_m2 > Decimal("0"):
        area = direct_area_m2.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        return FormulaResult(
            quantity=area,
            unit="m2",
            formula_id="FORMULA_TILE_DIRECT_AREA_V1",
            description="Прямая площадь повреждённой плитки",
            trace=f"S = {area} m2",
        )

    if damaged_tiles_count is not None and damaged_tiles_count > 0:
        one_tile = tile_area_m2 if (tile_area_m2 is not None and tile_area_m2 > Decimal("0")) else DEFAULT_TILE_AREA_M2
        area = (Decimal(str(damaged_tiles_count)) * one_tile).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        return FormulaResult(
            quantity=area,
            unit="m2",
            formula_id="FORMULA_TILE_COUNT_TO_AREA_V1",
            description="Площадь замены плитки (количество * площадь плитки)",
            trace=f"S = {damaged_tiles_count} шт * {one_tile} m2 = {area} m2",
        )

    raise ValueError("Для расчёта плитки необходимо указать либо direct_area_m2, либо damaged_tiles_count > 0")


def calculate_parking_waterproofing_area(
    leak_area_m2: Decimal | None = None,
    length_m: Decimal | None = None,
    width_m: Decimal | None = None,
) -> FormulaResult:
    """Расчёт площади локального восстановления гидроизоляции парковки.
    
    Формула: S = S_пятна * 1.15 (с технологическим нахлёстом).
    """
    if leak_area_m2 is not None and leak_area_m2 > Decimal("0"):
        base_area = leak_area_m2
    elif length_m is not None and width_m is not None and length_m > Decimal("0") and width_m > Decimal("0"):
        base_area = length_m * width_m
    else:
        raise ValueError("Для расчёта гидроизоляции требуется указать leak_area_m2 или (length_m и width_m)")

    total_area = (base_area * WATERPROOFING_MARGIN_FACTOR).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
    return FormulaResult(
        quantity=total_area,
        unit="m2",
        formula_id="FORMULA_PARKING_WATERPROOFING_V1",
        description="Площадь гидроизоляции с технологическим нахлёстом (+15%)",
        trace=f"S = {base_area} m2 * {WATERPROOFING_MARGIN_FACTOR} = {total_area} m2",
    )
