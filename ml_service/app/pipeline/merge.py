"""Слияние данных разнородных источников (CV, текст, пользователь) с сохранением Provenance."""
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.cv.schemas import CVInferenceResult
from app.llm.schemas import NormalizedDefectDescription
from app.ocr.schemas import DocumentExtractionResult
from app.schemas.common import ExtractedField, SourceType
from app.schemas.request import JobRequestDTO, KnownMeasurementDTO
from app.schemas.response import DetectedDefectDTO

DEFECT_NAMES = {
    "facade_crack": "Трещина фасада",
    "tile_chip": "Скол плитки",
    "parking_leak": "Протечка парковки",
}

TILE_MEASUREMENT_KEYS = frozenset({"count", "damaged_tiles_count", "tile_area_m2"})
PARKING_MEASUREMENT_KEYS = frozenset({"leak_area_m2"})
CRACK_MEASUREMENT_KEYS = frozenset(
    {"length_m", "length", "width_m", "width", "depth_m", "depth"}
)
AREA_MEASUREMENT_KEYS = frozenset({"area_m2", "area"})


def _unit_for_parameter(parameter_name: str) -> str:
    """Определяет единицу измерения по имени физического параметра."""
    if parameter_name.endswith("_m2") or parameter_name in {"area", "tile_area", "leak_area"}:
        return "m2"
    if parameter_name.endswith("_m3") or parameter_name == "volume":
        return "m3"
    if parameter_name.endswith("_m") or parameter_name in {
        "length",
        "width",
        "depth",
        "height",
        "thickness",
        "perimeter",
    }:
        return "m"
    return "pcs"


def _compatible_defect_codes(parameter_name: str) -> set[str]:
    """Возвращает типы дефектов, для которых параметр имеет физический смысл."""
    if parameter_name in TILE_MEASUREMENT_KEYS:
        return {"tile_chip"}
    if parameter_name in PARKING_MEASUREMENT_KEYS:
        return {"parking_leak"}
    if parameter_name in CRACK_MEASUREMENT_KEYS:
        return {"facade_crack", "parking_leak"}
    if parameter_name in AREA_MEASUREMENT_KEYS:
        return {"tile_chip", "parking_leak"}
    return set()


def _infer_defect_code(measurements: list[KnownMeasurementDTO]) -> str | None:
    """Выводит тип дефекта из набора пользовательских измерений, если он однозначен."""
    keys = {m.parameter_name for m in measurements}
    if keys & TILE_MEASUREMENT_KEYS:
        return "tile_chip"
    if keys & PARKING_MEASUREMENT_KEYS:
        return "parking_leak"
    if keys & CRACK_MEASUREMENT_KEYS:
        return "facade_crack"
    # area_m2 без других признаков неоднозначна (плитка или парковка) —
    # не угадываем тип, чтобы не подобрать неверную расценку.
    return None


def merge_defect_sources(
    request: JobRequestDTO,
    cv_result: CVInferenceResult | None,
    text_norm: NormalizedDefectDescription | None,
    ocr_results: list[DocumentExtractionResult] | None = None,
) -> list[DetectedDefectDTO]:
    """Объединяет детекции CV, OCR-документы, извлечённый текст и явные измерения пользователя."""
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
            defects_by_type[d_code].measurements[param] = ExtractedField[Decimal](
                field_name=param,
                value=val,
                unit=_unit_for_parameter(param),
                source_type=SourceType.USER,
                source_ref="user_description_text",
                confidence=None,
            )

    # 2.5. Добавляем данные из актов и документов (OCR)
    if ocr_results:
        from app.llm.mock_provider import MockLLMProvider
        ocr_extractor = MockLLMProvider()
        for doc in ocr_results:
            for page in doc.pages:
                if not page.text:
                    continue
                parsed = ocr_extractor.complete_structured(page.text, NormalizedDefectDescription)
                doc_code = parsed.detected_defect_type
                if doc_code:
                    if doc_code not in defects_by_type:
                        defects_by_type[doc_code] = DetectedDefectDTO(
                            defect_id=f"def-ocr-{uuid4().hex[:8]}",
                            defect_type_code=doc_code,
                            defect_type_name=DEFECT_NAMES.get(doc_code, doc_code),
                            confidence=page.confidence or 0.85,
                            location_description=parsed.location_details,
                            measurements={},
                        )
                    for param, val in parsed.extracted_measurements.items():
                        if param not in defects_by_type[doc_code].measurements:
                            defects_by_type[doc_code].measurements[param] = ExtractedField[Decimal](
                                field_name=param,
                                value=val,
                                unit=_unit_for_parameter(param),
                                source_type=SourceType.OCR,
                                source_ref=f"{doc.file_name}:p{page.page_number}",
                                confidence=page.confidence,
                            )

    # 3. Приоритетное наложение явно переданных измерений пользователя (known_measurements).
    # Они применяются последними и перекрывают измерения, извлечённые из текста.
    if request.known_measurements:
        target_defects = list(defects_by_type.values())

        if not target_defects:
            inferred_code = _infer_defect_code(request.known_measurements)
            if inferred_code is not None:
                d_obj = DetectedDefectDTO(
                    defect_id=f"def-known-{uuid4().hex[:8]}",
                    defect_type_code=inferred_code,
                    defect_type_name=DEFECT_NAMES.get(inferred_code, inferred_code),
                    confidence=None,
                    measurements={},
                )
                defects_by_type[inferred_code] = d_obj
                target_defects = [d_obj]

        for m in request.known_measurements:
            compatible = [
                defect
                for defect in target_defects
                if not _compatible_defect_codes(m.parameter_name)
                or defect.defect_type_code in _compatible_defect_codes(m.parameter_name)
            ]
            # Для единственного дефекта применяем явное измерение пользователя,
            # даже если эвристика не смогла определить совместимость.
            if not compatible and len(target_defects) == 1:
                compatible = target_defects

            for defect in compatible:
                defect.measurements[m.parameter_name] = ExtractedField[Decimal](
                    field_name=m.parameter_name,
                    value=m.numeric_value,
                    unit=m.unit_code,
                    source_type=SourceType.USER,
                    source_ref=m.source_notes or "known_measurements_input",
                    confidence=None,
                )

    return list(defects_by_type.values())
