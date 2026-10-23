"""Engine и сессии SQLAlchemy 2.0 для PostgreSQL (psycopg3, sync).

Engine создаётся лениво: импорт приложения не требует доступной БД и не
подставляет фиктивный `DATABASE_URL`. Если строка подключения не задана,
`get_engine()` падает с понятной ошибкой конфигурации.

Схему создаёт только `db/001_init.sql`. Здесь нет и не должно быть
`Base.metadata.create_all()`.
"""
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Вернуть singleton-engine, созданный из `DATABASE_URL`."""
    database_url = get_settings().database_url.strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL не задан. Скопируйте backend/.env.example в backend/.env "
            "и укажите строку подключения PostgreSQL (драйвер psycopg3)."
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Вернуть singleton-фабрику сессий, привязанную к engine."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI-зависимость: выдать сессию и гарантированно закрыть её.

    Коммит/откат делает вызывающий слой (сервис/репозиторий). Зависимость
    только управляет жизненным циклом соединения.
    """
    try:
        session = get_sessionmaker()()
    except RuntimeError as exc:
        raise AppError(
            503,
            "DB_UNAVAILABLE",
            "База данных не настроена или временно недоступна.",
        ) from exc
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Контекстный менеджер для скриптов и фоновых задач.

    Коммитит при успешном выходе и откатывает транзакцию при исключении.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> None:
    """Проверить, что БД доступна (для readiness-проверок и диагностики)."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
