"""Оркестрация MVP-сметы и сохранение трассировки в PostgreSQL."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.adapters.ml_pipeline import MLPipelineAdapter
from app.core.errors import AppError
from app.models.ai import AiRun
from app.models.defects import Defect
from app.models.estimates import Estimate, EstimateItem
from app.repositories.estimate_repository import EstimateRepository
from app.schemas.estimate import EstimateOut, EstimateRunOut, EstimateRunResult


class EstimateService:
    def __init__(
        self,
        db: Session,
        user_id: UUID,
        ml_adapter: MLPipelineAdapter,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.ml_adapter = ml_adapter
        self.repository = EstimateRepository(db)

    def _request(self, request_id: UUID):
        request = self.repository.request(request_id)
        if request is None:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        return request

    def _payload(self, request: Any) -> dict[str, Any]:
        building = self.repository.building(request.building_id)
        measurements = self.repository.measurements(request.request_id)
        return {
            "schema_version": "1.0",
            "request_id": str(request.request_id),
            "job_id": str(uuid4()),
            "description_text": request.description,
            "files": self.repository.photos(request.request_id),
            "building": {
                "building_id": str(request.building_id),
                "building_type": building.building_type if building else None,
                "wall_material": building.wall_material if building else None,
                "construction_year": building.construction_year if building else None,
                "additional_properties": (
                    building.additional_properties if building else {}
                ),
            },
            "known_measurements": [
                {
                    "parameter_name": item.parameter_code,
                    "numeric_value": str(item.value),
                    "unit_code": item.unit_code,
                    "source_notes": "request measurement",
                }
                for item in measurements
            ],
            "pipeline_version": "v2.0",
        }

    def run(self, request_id: UUID) -> EstimateRunResult:
        request = self._request(request_id)
        payload = self._payload(request)
        run = self.repository.create_run(
            request_id=request_id,
            pipeline_version=payload["pipeline_version"],
            input_snapshot=payload,
        )
        request.status = "processing"
        try:
            self.db.commit()
        except (IntegrityError, OperationalError) as exc:
            self.db.rollback()
            raise AppError(
                503 if isinstance(exc, OperationalError) else 409,
                "DB_UNAVAILABLE" if isinstance(exc, OperationalError) else "CONFLICT",
                "Не удалось сохранить запуск обработки.",
            ) from exc
        try:
            response = self.ml_adapter.process(payload)
            result = self._persist_response(request, run, payload, response)
            self.db.commit()
            return result
        except AppError:
            self.db.rollback()
            self._mark_failed(request_id, run.run_id, "ML Service недоступен.")
            raise
        except (IntegrityError, OperationalError) as exc:
            self.db.rollback()
            raise AppError(
                503 if isinstance(exc, OperationalError) else 409,
                "DB_UNAVAILABLE" if isinstance(exc, OperationalError) else "CONFLICT",
                "Не удалось сохранить результат обработки.",
            ) from exc
        except Exception as exc:
            self.db.rollback()
            self._mark_failed(request_id, run.run_id, "Ошибка обработки MVP-сметы.")
            raise AppError(500, "INTERNAL_ERROR", "Не удалось сформировать смету.") from exc

    def _mark_failed(self, request_id: UUID, run_id: UUID, message: str) -> None:
        run = self.db.get(AiRun, run_id)
        request = self.repository.request(request_id)
        if run is None or request is None:
            return
        run.status = "failed"
        run.error_message = message
        run.completed_at = datetime.now(timezone.utc)
        request.status = "failed"
        try:
            self.db.commit()
        except (IntegrityError, OperationalError):
            self.db.rollback()

    def _persist_response(
        self,
        request: Any,
        run: AiRun,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> EstimateRunResult:
        status = str(response.get("status", "failed"))
        run.status = {
            "completed": "completed",
            "needs_review": "completed",
            "needs_clarification": "needs_clarification",
        }.get(status, "failed")
        run.completed_at = datetime.now(timezone.utc)

        defects = response.get("defects") or []
        nlp_result = self.repository.add_result(
            run=run,
            request_id=request.request_id,
            module_type="nlp",
            result_data={"defects": defects, "status": status},
        )
        self.repository.add_result(
            run=run,
            request_id=request.request_id,
            module_type="cv",
            result_data={"defects": defects, "status": "completed"},
        )
        rag_result = self.repository.add_result(
            run=run,
            request_id=request.request_id,
            module_type="rag",
            result_data={
                "estimate_items": response.get("estimate_items", []),
                "status": status,
            },
        )

        persisted_defects: dict[str, Defect] = {}
        for defect_data in defects:
            code = defect_data.get("defect_type_code")
            defect_type = self.repository.defect_type(str(code))
            if defect_type is None:
                continue
            defect = self.repository.defect_by_type(
                request.request_id, defect_type.defect_type_id
            )
            if defect is None:
                defect = self.repository.add_defect(
                    request_id=request.request_id,
                    defect_type_id=defect_type.defect_type_id,
                    result_id=nlp_result.ai_result_id,
                    description=defect_data.get("defect_type_name", str(code)),
                    location=defect_data.get("location_description"),
                )
            else:
                defect.source_ai_result_id = nlp_result.ai_result_id
                defect.location_description = defect_data.get("location_description")
            persisted_defects[str(defect_data.get("defect_id"))] = defect

            for field_name, field in (defect_data.get("measurements") or {}).items():
                if field.get("value") is None:
                    continue
                self.repository.add_measurement(
                    request_id=request.request_id,
                    defect_id=defect.defect_id,
                    result_id=nlp_result.ai_result_id,
                    parameter_code=field_name,
                    value=field["value"],
                    unit_code=field.get("unit") or "pcs",
                )

        if status == "needs_clarification":
            request.status = "needs_clarification"
            return EstimateRunResult(
                run=EstimateRunOut.model_validate(run),
                clarification_questions=response.get("clarification_questions", []),
                warnings=response.get("warnings", []),
                audit_trail=response.get("audit_trail", []),
            )
        if status not in {"completed", "needs_review"}:
            run.error_message = "ML Service не сформировал сметные позиции."
            request.status = "failed"
            return EstimateRunResult(
                run=EstimateRunOut.model_validate(run),
                warnings=response.get("warnings", []),
                audit_trail=response.get("audit_trail", []),
            )

        estimate_status = "needs_review" if status == "needs_review" else "draft"
        estimate = self.repository.create_estimate(
            request_id=request.request_id,
            run_id=run.run_id,
            version=self.repository.next_version(request.request_id),
            snapshot=payload,
            total_cost=response.get("total_cost"),
            status=estimate_status,
            currency=response.get("currency", "RUB"),
        )
        for item in response.get("estimate_items", []):
            rate = self.repository.rate(str(item.get("rate_code")))
            defect = persisted_defects.get(str(item.get("defect_id")))
            quantity = Decimal(str(item["quantity"]))
            unit_price = Decimal(str(item["base_price"]))
            line_total = Decimal(str(item["line_total"]))
            self.repository.add_item(
                EstimateItem(
                    estimate_id=estimate.estimate_id,
                    request_id=request.request_id,
                    defect_id=defect.defect_id if defect else None,
                    rate_id=rate.rate_id if rate else None,
                    work_name=item["work_name"],
                    quantity=quantity,
                    unit_code=item["unit"],
                    unit_price=unit_price,
                    coefficient=rate.rate_unit_multiplier if rate else Decimal("1"),
                    base_cost=line_total,
                    additional_materials_cost=Decimal("0"),
                    total_cost=line_total,
                    calculation_details={
                        "formula_id": item.get("formula_id"),
                        "calculation_trace": item.get("calculation_trace", []),
                    },
                    validation_status="valid" if rate else "needs_review",
                    source_snapshot={
                        "origin": "ml_service",
                        "source_ref": item.get("source_ref"),
                        "rate_code": item.get("rate_code"),
                    },
                )
            )
        request.status = "ready_for_review"
        return EstimateRunResult(
            run=EstimateRunOut.model_validate(run),
            estimate=EstimateOut.model_validate(
                estimate
            ).model_copy(update={"items": self.repository.items(estimate.estimate_id)}),
            warnings=response.get("warnings", []),
            audit_trail=response.get("audit_trail", []),
        )

    def latest(self, request_id: UUID) -> EstimateRunResult:
        request = self._request(request_id)
        estimate = self.repository.latest_estimate(request.request_id)
        if estimate is None:
            raise AppError(404, "NOT_FOUND", "Для заявки ещё нет сметы.")
        run = self.db.get(AiRun, estimate.based_on_run_id) if estimate.based_on_run_id else None
        if run is None:
            raise AppError(500, "INTERNAL_ERROR", "У сметы отсутствует запуск пайплайна.")
        return EstimateRunResult(
            run=EstimateRunOut.model_validate(run),
            estimate=EstimateOut.model_validate(estimate).model_copy(
                update={"items": self.repository.items(estimate.estimate_id)}
            ),
        )
