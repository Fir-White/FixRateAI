"""Слияние данных разнородных источников (CV, текст, пользователь) с сохранением Provenance."""
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.cv.schemas import CVInferenceResult
from app.llm.schemas import NormalizedDefectDescription
from app.schemas.common import ExtractedField, SourceType, ValidationStatus
from app.schemas.request import JobRequestDTO
from app.schemas.response import DetectedDefectDTO

DEFECT_NAMES = {
    "facade_crack": "Трещина фасада",
    "tile_chip": "Скол плитки",
    "parking_leak": "Протечка парковки",
}


def merge_defect_sources(
    request: JobRequestDTO,
    cv_result: CVInferenceResult | None,
    text_norm: NormalizedDefectDescription | None,
) -> list[DetectedDefectDTO]:
    """Объединяет детекции CV, извлечённый текст и явные измерения пользователя."""
    defects_by_type: dict[str, DetectedDefectDTO] = {}

    # 1. Добавляем дефекты от CV
    if cv_result and cv_result.status == "completed":
        for det in cv_result.detections:
            d_code = det.class_name
            d_name = DEFECT_NAMES.get(d_code, d_code)
            d_id = f"def-cv-{uuid4().hex[:8]}"

            defects_by_type[d_code] = DetectedDefectDTO(
                defect_id=d_id,
                defect_type_code=d_code,
                defect_type_name=d_name,
                confidence=det.confidence,
                location_description=None,
                measurements={},
            )

    # 2. Добавляем дефекты из текста (если CV не обнаружил или подтверждает)
    if text_norm and text_norm.detected_defect_type:
        d_code = text_norm.detected_defect_type
        d_name = DEFECT_NAMES.get(d_code, d_code)

        if d_code not in defects_by_type:
            defects_by_type[d_code] = DetectedDefectDTO(
                defect_id=f"def-txt-{uuid4().hex[:8]}",
                defect_type_code=d_code,
                defect_type_name=d_name,
                confidence=0.80,
                location_description=text_norm.location_details,
                measurements={},
            )
        else:
            # Обновляем локализацию
            if text_norm.location_details and not defects_by_type[d_code].location_description:
                defects_by_type[d_code].location_description = text_norm.location_details

        # Переносим измерения из текста с source_type=USER (со слов заявителя)
        for param, val in text_norm.extracted_measurements.items():
            unit = "m" if "length" in param or "width" in param else ("m2" if "area" in param else "pcs")
            defects_by_type[d_code].measurements[param] = ExtractedField[Decimal](
                field_name=param,
                value=val,
                unit=unit,
                source_type=SourceType.USER,
                source_ref="user_description_text",
                confidence=None,
            )

    # 3. Приоритетное наложение явно переданных измерений пользователя (known_measurements)
    if request.known_measurements:
        # Если дефект один или дефектов пока нет, создаём дефект по умолчанию либо дополняем существующие
        target_defects = list(defects_by_type.values())
        if not target_defects:
            # Создаём дефект по умолчанию, если передан параметр
            first_param = request.known_measurements[0].parameter_name
            d_code = "facade_crack" if "length" in first_param else "tile_chip"
            d_obj = DetectedDefectDTO(
                defect_id=f"def-known-{uuid4().hex[:8]}",
                defect_type_code=d_code,
                defect_type_name=DEFECT_NAMES.get(d_code, d_code),
                confidence=None,
                measurements={},
            )
            defects_by_type[d_code] = d_obj
            target_defects = [d_obj]

        for m in request.known_measurements:
            for defect in target_defects:
                defect.measurements[m.parameter_name] = ExtractedField[Decimal](
                    field_name=m.parameter_name,
                    value=m.numeric_value,
                    unit=m.unit_code,
                    source_type=SourceType.USER,
                    source_ref=m.source_notes or "known_measurements_input",
                    confidence=None,
                )

    return list(defects_by_type.values())
