"""Проверки конфигурации engine/session без обязательной БД."""
import pytest

from app.db import session as db_session


def test_engine_requires_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    db_session.get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            db_session.get_engine()
    finally:
        db_session.get_settings.cache_clear()
        db_session.get_engine.cache_clear()
        db_session.get_sessionmaker.cache_clear()
