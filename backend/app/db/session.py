"""Explicit, synchronous session lifecycle; no connection is made at import."""
from collections.abc import Iterator
from contextlib import contextmanager
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker, SessionTransactionOrigin


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    try:
        parsed = make_url(url)
        _ = parsed.port
    except Exception:
        raise ValueError("Invalid DATABASE_URL") from None
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Use a PostgreSQL URL with the psycopg driver")
    return create_engine(parsed, pool_pre_ping=True, hide_parameters=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory.begin() as session:
        yield session


def session_dependency(factory: sessionmaker[Session]):
    """FastAPI dependency: services must commit before returning a response."""
    def dependency() -> Iterator[Session]:
        with factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise
    return dependency


@contextmanager
def service_transaction(session: Session) -> Iterator[Session]:
    """A service owns one transaction and commits before it returns.

    An existing autobegun transaction (for example an authorisation read) is
    part of the same unit of work and is committed or rolled back in full.
    Explicitly managed outer transactions remain the caller's responsibility.
    """
    active = session.get_transaction()
    if session.in_nested_transaction() or (active is not None and active.origin != SessionTransactionOrigin.AUTOBEGIN):
        raise RuntimeError("service cannot own an explicitly managed transaction")
    if active is None:
        session.begin()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
