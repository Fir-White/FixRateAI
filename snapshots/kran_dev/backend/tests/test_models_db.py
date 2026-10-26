"""Интеграционная проверка ORM-моделей против реальной схемы PostgreSQL.

Тест запускается только при заданном `DATABASE_URL` и пропускается в обычном
`pytest -q`, чтобы unit-тесты не требовали Docker. DDL должен быть уже
применён из `db/001_init.sql`.
"""
import os
from collections.abc import Iterator

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.models import Base

pytestmark = pytest.mark.integration


def _database_url() -> str:
    return (os.getenv("DATABASE_URL") or get_settings().database_url).strip()


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL не задан: интеграционный тест моделей пропущен")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - зависит от окружения
        engine.dispose()
        pytest.fail(f"DATABASE_URL задан, но PostgreSQL недоступен: {exc}")
    yield engine
    engine.dispose()


def _model_pg_type(column_type) -> str:
    """Ожидаемый `format_type` PostgreSQL для типа SQLAlchemy."""
    if isinstance(column_type, PG_UUID):
        return "uuid"
    if isinstance(column_type, TSVECTOR):
        return "tsvector"
    if isinstance(column_type, JSONB):
        return "jsonb"
    if isinstance(column_type, Vector):
        return "vector" if column_type.dim is None else f"vector({column_type.dim})"
    if isinstance(column_type, Boolean):
        return "boolean"
    if isinstance(column_type, SmallInteger):
        return "smallint"
    if isinstance(column_type, BigInteger):
        return "bigint"
    if isinstance(column_type, Integer):
        return "integer"
    if isinstance(column_type, DateTime):
        if not column_type.timezone:
            return "timestamp without time zone"
        return "timestamp with time zone"
    if isinstance(column_type, Date):
        return "date"
    if isinstance(column_type, Numeric):
        if column_type.precision is not None and column_type.scale is not None:
            return f"numeric({column_type.precision},{column_type.scale})"
        return "numeric"
    if isinstance(column_type, CHAR):
        return f"character({column_type.length})"
    if isinstance(column_type, Text):
        return "text"
    if isinstance(column_type, String):
        return f"character varying({column_type.length})"
    raise AssertionError(f"Неизвестный тип модели: {column_type!r}")


def _actual_pg_type(row) -> str:
    data_type = row["data_type"]
    if data_type == "USER-DEFINED":
        return row["udt_name"]
    if data_type == "character varying":
        return f"character varying({row['character_maximum_length']})"
    if data_type == "character":
        return f"character({row['character_maximum_length']})"
    if data_type == "numeric":
        return f"numeric({row['numeric_precision']},{row['numeric_scale']})"
    return data_type


def _model_foreign_keys(table) -> set[tuple]:
    result = set()
    for fk in table.foreign_key_constraints:
        local_columns = tuple(column.name for column in fk.columns)
        remote_columns = tuple(element.column.name for element in fk.elements)
        remote_table = fk.elements[0].column.table.name
        result.add(
            (
                fk.name,
                local_columns,
                remote_table,
                remote_columns,
                fk.ondelete,
            )
        )
    return result


def _actual_foreign_keys(inspector, table_name: str) -> set[tuple]:
    result = set()
    for fk in inspector.get_foreign_keys(table_name):
        result.add(
            (
                fk["name"],
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
                fk["options"].get("ondelete"),
            )
        )
    return result


def test_schema_tables_and_columns_match_models(engine):
    actual_tables = set(inspect(engine).get_table_names(schema="public"))
    assert actual_tables == set(Base.metadata.tables)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name, column_name, is_nullable, data_type, udt_name,
                       character_maximum_length, numeric_precision, numeric_scale,
                       is_generated, generation_expression
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                 ORDER BY table_name, ordinal_position
                """
            )
        ).mappings()
        actual_columns = {
            (row["table_name"], row["column_name"]): row for row in rows
        }

    expected_keys = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
    }
    assert set(actual_columns) == expected_keys

    for table in Base.metadata.tables.values():
        for column in table.columns:
            actual = actual_columns[(table.name, column.name)]
            assert actual["is_nullable"] == (
                "YES" if column.nullable else "NO"
            ), f"{table.name}.{column.name}: nullable"
            assert _actual_pg_type(actual) == _model_pg_type(
                column.type
            ), f"{table.name}.{column.name}: type"


def test_primary_keys_match_models(engine):
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        actual = inspector.get_pk_constraint(table.name)["constrained_columns"]
        expected = [column.name for column in table.primary_key.columns]
        assert list(actual) == expected, f"{table.name}: PK"


def test_foreign_keys_match_models(engine):
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        assert _actual_foreign_keys(inspector, table.name) == _model_foreign_keys(
            table
        ), f"{table.name}: FK"


def test_unique_constraints_match_models(engine):
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        actual = {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints(table.name)
        }
        expected = {
            (constraint.name, tuple(column.name for column in constraint.columns))
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert actual == expected, f"{table.name}: UNIQUE"


def test_indexes_match_models(engine):
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        actual = {
            index["name"]
            for index in inspector.get_indexes(table.name)
            if not index.get("duplicates_constraint")
        }
        expected = {index.name for index in table.indexes}
        assert actual == expected, f"{table.name}: indexes"


def test_check_constraints_match_models(engine):
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT conrelid::regclass::text AS table_name, conname
                  FROM pg_constraint
                 WHERE connamespace = 'public'::regnamespace
                   AND contype = 'c'
                """
            )
        )
        actual = {(row.table_name, row.conname) for row in rows}

    expected = {
        (table.name, constraint.name)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert actual == expected


def test_generated_search_vector_matches_ddl(engine):
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT is_generated, generation_expression
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'normative_chunks'
                   AND column_name = 'search_vector'
                """
            )
        ).one()
    assert row.is_generated == "ALWAYS"
    assert "to_tsvector" in row.generation_expression


def test_special_index_definitions_match_ddl(engine):
    expected_fragments = {
        "uq_users_email_lower": "lower",
        "uq_defect_single_primary_photo": "WHERE is_primary",
        "uq_measure_current_per_parameter": "WHERE is_current",
        "idx_rates_work_name": "to_tsvector",
        "idx_rates_code": "rate_code",
        "uq_norm_sources_current_series": "WHERE is_current",
        "idx_chunks_search_vector": "gin",
    }
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT indexname, indexdef
                  FROM pg_indexes
                 WHERE schemaname = 'public'
                   AND indexname = ANY(:names)
                """
            ),
            {"names": list(expected_fragments)},
        )
        actual = {row.indexname: row.indexdef for row in rows}

    assert set(actual) == set(expected_fragments)
    for index_name, fragment in expected_fragments.items():
        assert fragment in actual[index_name], index_name


def test_app_engine_connects(engine):
    from app.db.session import check_database_connection

    check_database_connection()


def test_app_session_helpers_work(engine):
    from app.db.session import get_db, session_scope

    with session_scope() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    dependency = get_db()
    session = next(dependency)
    try:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        dependency.close()
