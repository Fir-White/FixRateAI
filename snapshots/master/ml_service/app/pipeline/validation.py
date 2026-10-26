"""Валидация достаточности данных и генерация запросов на уточнение (needs_clarification)."""
from typing import NamedTuple
from app.schemas.response import ClarificationQuestionDTO, DetectedDefectDTO


class ValidationResult(NamedTuple):
    """Результат проверки полноты параметров."""
    is_complete: bool
    questions: list[ClarificationQuestionDTO]
    warnings: list[str]


def validate_defect_completeness(defects: list[DetectedDefectDTO]) -> ValidationResult:
    """Проверяет наличие обязательных физических параметров для сметного расчёта каждого дефекта."""
    questions: list[ClarificationQuestionDTO] = []
    warnings: list[str] = []

    if not defects:
        # Если ни CV, ни текст не обнаружили дефект
        questions.append(
            ClarificationQuestionDTO(
                code="NO_DEFECT_DETECTED",
                field_name="defect_description",
                question_text="Не удалось обнаружить строительный дефект на фото или в описании. Пожалуйста, опишите проблему подробнее.",
                expected_unit=None,
                severity="blocking",
            )
        )
        return ValidationResult(is_complete=False, questions=questions, warnings=warnings)

    for defect in defects:
        code = defect.defect_type_code
        meas = defect.measurements

        if code == "facade_crack":
            # Требуется длина трещины
            has_len = any(k in meas for k in ("length_m", "length"))
            if not has_len:
                questions.append(
                    ClarificationQuestionDTO(
                        code="MISSING_CRACK_LENGTH",
                        field_name="length_m",
                        question_text="Укажите ориентировочную длину трещины на фасаде в метрах",
                        expected_unit="m",
                        severity="blocking",
                    )
                )

        elif code == "tile_chip":
            # Требуется количество плиток или площадь
            has_count_or_area = any(k in meas for k in ("count", "damaged_tiles_count", "area_m2", "area"))
            if not has_count_or_area:
                questions.append(
                    ClarificationQuestionDTO(
                        code="MISSING_TILE_COUNT",
                        field_name="count",
                        question_text="Укажите количество повреждённых плиток (в штуках) или площадь замены (м2)",
                        expected_unit="pcs",
                        severity="blocking",
                    )
                )

        elif code == "parking_leak":
            # Требуется площадь пятна либо длина и ширина
            has_area = any(k in meas for k in ("area_m2", "area", "leak_area_m2"))
            has_dims = ("length_m" in meas or "length" in meas) and ("width_m" in meas or "width" in meas)
            if not (has_area or has_dims):
                questions.append(
                    ClarificationQuestionDTO(
                        code="MISSING_LEAK_AREA",
                        field_name="area_m2",
                        question_text="Укажите примерную площадь протечки/влажного пятна на парковке (м2)",
                        expected_unit="m2",
                        severity="blocking",
                    )
                )

    is_complete = len(questions) == 0
    return ValidationResult(is_complete=is_complete, questions=questions, warnings=warnings)
