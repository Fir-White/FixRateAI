"""Бизнес-правила жизненного цикла заявок."""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.core import User
from app.models.requests import RepairRequest
from app.repositories.request_repository import RequestRepository
from app.schemas.request import RequestCreate, RequestOut, RequestUpdate


EDITABLE_STATUSES = {"created", "needs_clarification"}
REVIEW_STATUSES = {"created", "needs_clarification", "ready_for_review"}


class RequestService:
    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user
        self.repository = RequestRepository(db)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except (IntegrityError, OperationalError) as exc:
            self.db.rollback()
            raise AppError(
                503 if isinstance(exc, OperationalError) else 409,
                "DB_UNAVAILABLE" if isinstance(exc, OperationalError) else "CONFLICT",
                "База данных временно недоступна."
                if isinstance(exc, OperationalError)
                else "Данные заявки конфликтуют с текущим состоянием.",
            ) from exc

    def _load(self, request_id: UUID) -> RepairRequest:
        request = self.repository.get(request_id)
        if request is None:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        return request

    def _output(self, request: RepairRequest) -> RequestOut:
        return RequestOut.model_validate(request).model_copy(
            update={
                "photos": self.repository.photos(request.request_id),
                "measurements": self.repository.measurements(request.request_id),
            }
        )

    def create(self, data: RequestCreate) -> RequestOut:
        if not self.repository.building_exists(data.building_id):
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Объект здания не найден или неактивен.",
                [{"field": "building_id", "issue": "building not found"}],
            )
        request = self.repository.create(
            RepairRequest(
                building_id=data.building_id,
                created_by=self.user.user_id,
                title=data.title,
                description=data.description,
                location_description=data.location_description,
            )
        )
        if data.photos:
            self.repository.add_photos(
                request.request_id,
                [photo.model_dump() for photo in data.photos],
            )
        if not self.repository.photos_belong_to_request(
            request.request_id, data.photo_ids
        ):
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Одно или несколько фото не принадлежат заявке.",
                [{"field": "photo_ids", "issue": "photo not found"}],
            )
        if data.measurements:
            self.repository.add_measurements(
                request.request_id,
                self.user.user_id,
                [item.model_dump() for item in data.measurements],
            )
        self._commit()
        return self._output(request)

    def get(self, request_id: UUID) -> RequestOut:
        return self._output(self._load(request_id))

    def list(
        self, *, limit: int, offset: int, status: str | None, building_id: UUID | None
    ) -> tuple[list[RequestOut], int]:
        items, total = self.repository.list(
            limit=limit, offset=offset, status=status, building_id=building_id
        )
        return [self._output(item) for item in items], total

    def update(self, request_id: UUID, data: RequestUpdate) -> RequestOut:
        request = self._load(request_id)
        values = data.model_dump(exclude_unset=True, exclude={"measurements"})
        if request.status not in EDITABLE_STATUSES and values.keys() - {
            "status",
            "cancellation_reason",
        }:
            raise AppError(
                409,
                "CONFLICT",
                "Заявку нельзя редактировать в текущем статусе.",
            )
        if "status" in values:
            if request.status not in REVIEW_STATUSES:
                raise AppError(409, "CONFLICT", "Заявку нельзя отменить в текущем статусе.")
            values["cancellation_reason"] = data.cancellation_reason
        self.repository.update_fields(request, values)
        if data.measurements is not None:
            self.repository.add_measurements(
                request.request_id,
                self.user.user_id,
                [item.model_dump() for item in data.measurements],
            )
        self._commit()
        return self._output(request)
