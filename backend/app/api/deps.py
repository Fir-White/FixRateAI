"""Общие зависимости API."""
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.core import User


def get_current_user(
    db: Session = Depends(get_db),
) -> User:
    """Вернуть активного demo-пользователя до внедрения JWT."""
    email = get_settings().demo_user_email
    try:
        user = db.scalar(
            select(User).where(User.email == email, User.is_active.is_(True))
        )
    except OperationalError as exc:
        raise AppError(
            503,
            "DB_UNAVAILABLE",
            "База данных временно недоступна.",
        ) from exc

    if user is None:
        raise AppError(
            401,
            "UNAUTHORIZED",
            "Активный пользователь API не найден.",
            [{"field": "demo_user_email", "issue": "user not found or inactive"}],
        )
    return user


def parse_uuid(value: str, field: str) -> UUID:
    """Преобразовать UUID из path/query с единым кодом ошибки."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Некорректный идентификатор.",
            [{"field": field, "issue": "must be a UUID"}],
        ) from exc
