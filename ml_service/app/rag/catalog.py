"""Реестр и загрузчик эталонных расценок FixRate AI."""
import json
from pathlib import Path
from decimal import Decimal
from app.rag.schemas import NormSourceDTO, RateItem


class RatesCatalog:
    """Каталог расценок и нормативных источников."""

    def __init__(self, source: NormSourceDTO, rates: list[RateItem]) -> None:
        self.source = source
        self.rates = rates
        self._rates_by_code: dict[str, RateItem] = {r.rate_code: r for r in rates}
        self._rates_by_defect: dict[str, list[RateItem]] = {}
        for r in rates:
            for defect in r.applicable_defects:
                self._rates_by_defect.setdefault(defect, []).append(r)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "RatesCatalog":
        """Загружает каталог расценок из JSON-файла."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Файл каталога расценок не найден: {p}")

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        source = NormSourceDTO(**data["source"])
        rates = []
        for r_dict in data.get("rates", []):
            # Конвертируем числовые поля в Decimal
            r_dict["base_price"] = Decimal(str(r_dict["base_price"]))
            r_dict["rate_unit_multiplier"] = Decimal(str(r_dict.get("rate_unit_multiplier", 1)))
            rates.append(RateItem(**r_dict))

        return cls(source=source, rates=rates)

    def get_by_code(self, rate_code: str) -> RateItem | None:
        """Поиск расценки по точному коду."""
        return self._rates_by_code.get(rate_code)

    def get_by_defect_type(self, defect_type: str) -> list[RateItem]:
        """Возвращает все расценки, применимые к данному типу дефекта."""
        return self._rates_by_defect.get(defect_type, [])

    def list_all(self) -> list[RateItem]:
        """Возвращает полный список расценок."""
        return list(self.rates)
