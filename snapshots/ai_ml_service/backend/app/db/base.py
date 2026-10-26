"""Базовый класс декларативных моделей SQLAlchemy 2.0.

`Base.metadata` описывает таблицы для ORM, но НЕ является источником схемы.
Источник истины — `db/001_init.sql`; `create_all()` в проекте запрещён.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Общий базовый класс всех ORM-моделей FixRate AI."""
