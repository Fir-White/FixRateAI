"""Главный координатор сквозного пайплайна обработки FixRate AI."""
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.calculation.engine import CalculationEngine
from app.core.config import get_settings
from app.cv.schemas import CVInferenceResult
from app.cv.service import CVService
from app.llm.gateway import LLMGateway
from app.pipeline.merge import merge_defect_sources
from app.pipeline.state import InternalPipelineContext, PipelineStage
from app.pipeline.validation import validate_defect_completeness
from app.rag.catalog import RatesCatalog
from app.rag.hybrid import HybridRAGSearchEngine
from app.schemas.common import PipelineStatus
from app.schemas.request import JobRequestDTO
from app.schemas.response import EstimateItemDTO, JobResponseDTO

logger = logging.getLogger("app.pipeline.orchestrator")


class PipelineOrchestrator:
    """Оркестратор полного цикла анализа дефекта и расчёта сметы."""

    def __init__(
        self,
        cv_service: CVService | None = None,
        llm_gateway: LLMGateway | None = None,
        rag_engine: HybridRAGSearchEngine | None = None,
        calc_engine: CalculationEngine | None = None,
    ) -> None:
        settings = get_settings()
        self.cv_service = cv_service or CVService()
        self.llm_gateway = llm_gateway or LLMGateway()

        if rag_engine is not None:
            self.rag_engine = rag_engine
        else:
            cat_path = settings.base_dir / settings.rag_catalog_path
            catalog = RatesCatalog.from_json_file(cat_path)
            self.rag_engine = HybridRAGSearchEngine(catalog.list_all())

        self.calc_engine = calc_engine or CalculationEngine()

    def process_job(self, request: JobRequestDTO) -> JobResponseDTO:
        """Выполняет сквозной пайплайн по входному запросу."""
        start_time = time.perf_counter()
        ctx = InternalPipelineContext(request=request)
        ctx.audit_trail.append(f"Задача принята: job_id={request.job_id}, request_id={request.request_id}")

        # -------------------------------------------------------------
        # Этап 1: Компьютерное зрение (CV Inference)
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.CV_INFERENCE
        image_files = [f for f in request.files if f.file_type == "image"]
        if image_files:
            target_file = image_files[0]
            try:
                # Если передан путь к файлу
                if target_file.file_path and Path(target_file.file_path).is_file():
                    ctx.cv_result = self.cv_service.detect_image(target_file.file_path)
                elif target_file.file_bytes_base64:
                    import base64
                    raw_bytes = base64.b64decode(target_file.file_bytes_base64)
                    ctx.cv_result = self.cv_service.detect_image(raw_bytes)
                else:
                    # В режиме mock-тестирования при отсутствии физического файла вызываем детекцию dummy
                    from app.cv.image_io import Image
                    import io
                    dummy = Image.new("RGB", (640, 480), color="gray")
                    buf = io.BytesIO()
                    dummy.save(buf, format="JPEG")
                    ctx.cv_result = self.cv_service.detect_image(buf.getvalue())

                ctx.audit_trail.append(
                    f"CV инференс: статус={ctx.cv_result.status}, детекций={len(ctx.cv_result.detections)}"
                )
            except Exception as e:
                logger.warning("Ошибка при вызове CV для файла %s: %s", target_file.file_id, e)
                ctx.warnings.append(f"Ошибка анализа изображения {target_file.file_id}: {e}")

        # -------------------------------------------------------------
        # Этап 2: LLM нормализация текста описания
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.TEXT_NORMALIZATION
        if request.description_text:
            ctx.text_norm = self.llm_gateway.normalize_user_text(request.description_text)
            ctx.audit_trail.append(
                f"LLM разбор текста: тип={ctx.text_norm.detected_defect_type}, "
                f"измерений={len(ctx.text_norm.extracted_measurements)}"
            )

        # -------------------------------------------------------------
        # Этап 3: Слияние данных источников с сохранением Provenance
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.DATA_MERGE
        ctx.merged_defects = merge_defect_sources(
            request=request,
            cv_result=ctx.cv_result,
            text_norm=ctx.text_norm,
        )
        ctx.audit_trail.append(f"Слияние данных: сформировано дефектов={len(ctx.merged_defects)}")

        # -------------------------------------------------------------
        # Этап 4: Валидация полноты параметров (ветвление clarification)
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.VALIDATION
        val_result = validate_defect_completeness(ctx.merged_defects)

        if not val_result.is_complete:
            ctx.stage = PipelineStage.CLARIFICATION_REQUIRED
            ctx.status = PipelineStatus.NEEDS_CLARIFICATION
            ctx.clarification_questions = val_result.questions
            ctx.warnings.extend(val_result.warnings)
            ctx.audit_trail.append(
                f"Требуются уточнения: сформировано вопросов={len(ctx.clarification_questions)}"
            )

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return JobResponseDTO(
                job_id=request.job_id,
                request_id=request.request_id,
                status=ctx.status,
                pipeline_version=request.pipeline_version,
                processing_time_ms=elapsed_ms,
                defects=ctx.merged_defects,
                estimate_items=[],
                total_cost=None,
                clarification_questions=ctx.clarification_questions,
                warnings=ctx.warnings,
                audit_trail=ctx.audit_trail,
            )

        # -------------------------------------------------------------
        # Этап 5: RAG подбор расценок и проверка применимости
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.RAG_RETRIEVAL
        has_review_items = False

        for defect in ctx.merged_defects:
            query_str = f"{defect.defect_type_name} {defect.location_description or ''}"
            candidates = self.rag_engine.search(
                query=query_str,
                defect_type=defect.defect_type_code,
                top_k=3,
            )

            if not candidates or not candidates[0].applicability.is_applicable:
                ctx.warnings.append(f"Не удалось подобрать применимую расценку для дефекта {defect.defect_type_code}")
                continue

            chosen_candidate = candidates[0]
            if chosen_candidate.applicability.requires_review:
                has_review_items = True
                ctx.warnings.extend(chosen_candidate.applicability.warnings)

            # -------------------------------------------------------------
            # Этап 6: Детерминированный расчёт объёма и стоимости позиции
            # -------------------------------------------------------------
            ctx.stage = PipelineStage.CALCULATION
            # Извлекаем сырые значения параметров дефекта
            raw_measurements = {k: field.value for k, field in defect.measurements.items()}
            
            try:
                formula_res = self.calc_engine.calculate_work_quantity(
                    defect_type=defect.defect_type_code,
                    measurements=raw_measurements,
                )

                item = self.calc_engine.create_estimate_item(
                    rate_code=chosen_candidate.rate.rate_code,
                    work_name=chosen_candidate.rate.work_name,
                    quantity=formula_res.quantity,
                    unit=formula_res.unit,
                    base_price=chosen_candidate.rate.base_price,
                    source_ref=chosen_candidate.rate.rate_code,
                    formula_id=formula_res.formula_id,
                    quantity_trace=formula_res.trace,
                    unit_multiplier=chosen_candidate.rate.rate_unit_multiplier,
                )
                ctx.estimate_items.append(item)
                ctx.audit_trail.append(
                    f"Расчёт позиции '{item.rate_code}': объём={item.quantity} {item.unit}, сумма={item.line_total} RUB"
                )

            except Exception as e:
                logger.error("Ошибка расчёта объёма для дефекта %s: %s", defect.defect_id, e)
                ctx.warnings.append(f"Ошибка расчёта для дефекта {defect.defect_type_code}: {e}")

        # -------------------------------------------------------------
        # Этап 7: QA аудит и вычисление итоговой сметной стоимости
        # -------------------------------------------------------------
        ctx.stage = PipelineStage.QA_AUDIT
        total_cost = self.calc_engine.calculate_total_cost(ctx.estimate_items)
        ctx.audit_trail.append(f"Итоговая стоимость сметы: {total_cost} RUB")

        ctx.stage = PipelineStage.COMPLETED
        ctx.status = (
            PipelineStatus.NEEDS_REVIEW
            if has_review_items
            else PipelineStatus.COMPLETED
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return JobResponseDTO(
            job_id=request.job_id,
            request_id=request.request_id,
            status=ctx.status,
            pipeline_version=request.pipeline_version,
            processing_time_ms=elapsed_ms,
            defects=ctx.merged_defects,
            estimate_items=ctx.estimate_items,
            total_cost=total_cost,
            currency="RUB",
            clarification_questions=[],
            warnings=ctx.warnings,
            audit_trail=ctx.audit_trail,
        )
