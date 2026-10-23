"""SQL-доступ к заявкам без бизнес-правил."""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.defects import Defect, DefectMeasurement
from app.models.requests import RepairRequest, RequestPhoto


class RequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def building_exists(self, building_id: UUID) -> bool:
        from app.models.core import Building

        return self.db.scalar(
            select(func.count()).select_from(Building).where(
                Building.building_id == building_id,
                Building.is_active.is_(True),
            )
        ) == 1

    def photos_belong_to_request(
        self, request_id: UUID, photo_ids: Sequence[UUID]
    ) -> bool:
        if not photo_ids:
            return True
        count = self.db.scalar(
            select(func.count()).select_from(RequestPhoto).where(
                RequestPhoto.request_id == request_id,
                RequestPhoto.photo_id.in_(photo_ids),
            )
        )
        return count == len(set(photo_ids))

    def create(self, request: RepairRequest) -> RepairRequest:
        self.db.add(request)
        self.db.flush()
        return request

    def add_photos(
        self, request_id: UUID, photos: list[dict[str, object]]
    ) -> None:
        self.db.add_all(
            [
                RequestPhoto(request_id=request_id, **photo)
                for photo in photos
            ]
        )
        self.db.flush()

    def get(self, request_id: UUID) -> RepairRequest | None:
        return self.db.get(RepairRequest, request_id)

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None,
        building_id: UUID | None,
    ) -> tuple[list[RepairRequest], int]:
        filters = []
        if status:
            filters.append(RepairRequest.status == status)
        if building_id:
            filters.append(RepairRequest.building_id == building_id)

        query = (
            select(RepairRequest)
            .where(*filters)
            .order_by(RepairRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.scalars(query).all())
        total = self.db.scalar(
            select(func.count()).select_from(RepairRequest).where(*filters)
        ) or 0
        return items, total

    def photos(self, request_id: UUID) -> list[RequestPhoto]:
        return list(
            self.db.scalars(
                select(RequestPhoto)
                .where(RequestPhoto.request_id == request_id)
                .order_by(RequestPhoto.uploaded_at.asc())
            ).all()
        )

    def measurements(self, request_id: UUID) -> list[DefectMeasurement]:
        return list(
            self.db.scalars(
                select(DefectMeasurement)
                .where(
                    DefectMeasurement.request_id == request_id,
                    DefectMeasurement.is_current.is_(True),
                )
                .order_by(DefectMeasurement.created_at.asc())
            ).all()
        )

    def current_defect(self, request_id: UUID) -> Defect | None:
        return self.db.scalar(
            select(Defect)
            .where(Defect.request_id == request_id)
            .order_by(Defect.created_at.asc())
        )

    def add_measurements(
        self,
        request_id: UUID,
        user_id: UUID,
        measurements: list[dict[str, object]],
    ) -> None:
        defect = self.current_defect(request_id)
        if defect is None:
            defect = Defect(request_id=request_id, confirmation_status="suggested")
            self.db.add(defect)
            self.db.flush()

        current = self.measurements(request_id)
        by_parameter = {item.parameter_code: item for item in current}
        for data in measurements:
            previous = by_parameter.get(str(data["parameter_code"]))
            if previous:
                previous.is_current = False
            self.db.add(
                DefectMeasurement(
                    defect_id=defect.defect_id,
                    request_id=request_id,
                    parameter_code=str(data["parameter_code"]),
                    value=data["value"],
                    unit_code=str(data["unit_code"]),
                    source_type="manual",
                    recorded_by=user_id,
                    is_approximate=bool(data["is_approximate"]),
                    supersedes_measurement_id=(
                        previous.measurement_id if previous else None
                    ),
                )
            )
        self.db.flush()

    def update_fields(
        self, request: RepairRequest, values: dict[str, object]
    ) -> RepairRequest:
        for field, value in values.items():
            setattr(request, field, value)
        self.db.flush()
        return request
