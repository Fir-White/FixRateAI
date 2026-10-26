"""SQL-доступ к запускам пайплайна и версиям смет."""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai import AiResult, AiRun
from app.models.core import Building, DefectType
from app.models.defects import Defect, DefectMeasurement
from app.models.estimates import Estimate, EstimateItem
from app.models.norms import Rate
from app.models.requests import RepairRequest


class EstimateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def request(self, request_id: UUID) -> RepairRequest | None:
        return self.db.get(RepairRequest, request_id)

    def building(self, building_id: UUID) -> Building | None:
        return self.db.get(Building, building_id)

    def measurements(self, request_id: UUID) -> list[DefectMeasurement]:
        return list(
            self.db.scalars(
                select(DefectMeasurement).where(
                    DefectMeasurement.request_id == request_id,
                    DefectMeasurement.is_current.is_(True),
                )
            ).all()
        )

    def photos(self, request_id: UUID) -> list[dict[str, object]]:
        from app.models.requests import RequestPhoto

        return [
            {
                "file_id": str(photo.photo_id),
                "file_type": "image",
                "mime_type": photo.mime_type,
                "file_path": None,
            }
            for photo in self.db.scalars(
                select(RequestPhoto).where(RequestPhoto.request_id == request_id)
            ).all()
        ]

    def create_run(
        self,
        request_id: UUID,
        pipeline_version: str,
        input_snapshot: dict[str, object],
    ) -> AiRun:
        run = AiRun(
            request_id=request_id,
            status="running",
            pipeline_version=pipeline_version,
            input_snapshot=input_snapshot,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def add_result(
        self,
        *,
        run: AiRun,
        request_id: UUID,
        module_type: str,
        result_data: dict[str, object],
        status: str = "completed",
    ) -> AiResult:
        result = AiResult(
            run_id=run.run_id,
            request_id=request_id,
            module_type=module_type,
            model_name="mock",
            model_version=run.pipeline_version,
            input_reference={"source": "ml_service"},
            result_data=result_data,
            status=status,
            processing_time_ms=0,
        )
        self.db.add(result)
        self.db.flush()
        return result

    def defect_type(self, code: str) -> DefectType | None:
        return self.db.scalar(select(DefectType).where(DefectType.code == code))

    def defect(self, request_id: UUID, defect_id: UUID | None = None) -> Defect | None:
        query = select(Defect).where(Defect.request_id == request_id)
        if defect_id:
            query = query.where(Defect.defect_id == defect_id)
        return self.db.scalar(query.order_by(Defect.created_at.asc()))

    def defect_by_type(self, request_id: UUID, defect_type_id: UUID) -> Defect | None:
        return self.db.scalar(
            select(Defect)
            .where(
                Defect.request_id == request_id,
                Defect.defect_type_id == defect_type_id,
            )
            .order_by(Defect.created_at.asc())
        )

    def add_defect(
        self,
        *,
        request_id: UUID,
        defect_type_id: UUID,
        result_id: UUID,
        description: str,
        location: str | None,
    ) -> Defect:
        defect = Defect(
            request_id=request_id,
            defect_type_id=defect_type_id,
            source_ai_result_id=result_id,
            description=description,
            location_description=location,
            confirmation_status="suggested",
        )
        self.db.add(defect)
        self.db.flush()
        return defect

    def add_measurement(
        self,
        *,
        request_id: UUID,
        defect_id: UUID,
        result_id: UUID,
        parameter_code: str,
        value: object,
        unit_code: str,
    ) -> DefectMeasurement:
        existing = self.db.scalar(
            select(DefectMeasurement).where(
                DefectMeasurement.defect_id == defect_id,
                DefectMeasurement.parameter_code == parameter_code,
                DefectMeasurement.is_current.is_(True),
            )
        )
        if existing is not None:
            return existing
        measurement = DefectMeasurement(
            request_id=request_id,
            defect_id=defect_id,
            source_ai_result_id=result_id,
            parameter_code=parameter_code,
            value=value,
            unit_code=unit_code,
            source_type="derived",
            is_approximate=False,
        )
        self.db.add(measurement)
        self.db.flush()
        return measurement

    def next_version(self, request_id: UUID) -> int:
        return (self.db.scalar(
            select(func.max(Estimate.version)).where(Estimate.request_id == request_id)
        ) or 0) + 1

    def rate(self, rate_code: str) -> Rate | None:
        return self.db.scalar(select(Rate).where(Rate.rate_code == rate_code, Rate.is_active.is_(True)))

    def create_estimate(
        self,
        *,
        request_id: UUID,
        run_id: UUID,
        version: int,
        snapshot: dict[str, object],
        total_cost: object | None,
        status: str,
        currency: str,
    ) -> Estimate:
        estimate = Estimate(
            request_id=request_id,
            version=version,
            based_on_run_id=run_id,
            input_snapshot=snapshot,
            total_cost=total_cost,
            status=status,
            currency=currency,
        )
        self.db.add(estimate)
        self.db.flush()
        return estimate

    def add_item(self, item: EstimateItem) -> EstimateItem:
        self.db.add(item)
        self.db.flush()
        return item

    def latest_estimate(self, request_id: UUID) -> Estimate | None:
        return self.db.scalar(
            select(Estimate)
            .where(Estimate.request_id == request_id)
            .order_by(Estimate.version.desc())
        )

    def items(self, estimate_id: UUID) -> list[EstimateItem]:
        return list(self.db.scalars(
            select(EstimateItem).where(EstimateItem.estimate_id == estimate_id)
        ).all())
