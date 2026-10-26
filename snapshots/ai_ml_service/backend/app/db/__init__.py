"""Работа с PostgreSQL через SQLAlchemy 2.0 (sync).

Схема приходит только из `db/001_init.sql`; приложение не создаёт таблицы.
"""
from app.db.base import Base
from app.db.session import (
    check_database_connection,
    get_db,
    get_engine,
    get_sessionmaker,
    session_scope,
)

__all__ = [
    "Base",
    "check_database_connection",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "session_scope",
]
