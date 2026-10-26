"""Проверки ORM-моделей без подключения к БД (карточка 2)."""
from decimal import Decimal

from sqlalchemy import CheckConstraint, Float, Numeric, UniqueConstraint

from app.models import Base

EXPECTED_TABLES = {
    "ai_results",
    "ai_runs",
    "audit_events",
    "buildings",
    "defect_measurements",
    "defect_photos",
    "defect_types",
    "defects",
    "estimate_items",
    "estimate_materials",
    "estimates",
    "norm_sources",
    "normative_chunks",
    "rates",
    "repair_requests",
    "request_clarifications",
    "request_photos",
    "users",
}

# Все денежные и объёмные поля должны быть NUMERIC (Decimal), не float.
DECIMAL_COLUMNS = {
    ("buildings", "total_area"),
    ("defect_measurements", "value"),
    ("rates", "rate_unit_multiplier"),
    ("rates", "base_price"),
    ("estimates", "total_cost"),
    ("estimate_items", "quantity"),
    ("estimate_items", "unit_price"),
    ("estimate_items", "coefficient"),
    ("estimate_items", "base_cost"),
    ("estimate_items", "additional_materials_cost"),
    ("estimate_items", "total_cost"),
    ("estimate_materials", "quantity"),
    ("estimate_materials", "unit_price"),
    ("estimate_materials", "total_cost"),
}


def test_all_18_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_total_column_count_matches_ddl():
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 188


def test_no_float_columns():
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, Float), f"{table.name}.{column.name}"


def test_decimal_columns_are_numeric():
    for table_name, column_name in DECIMAL_COLUMNS:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, Numeric), f"{table_name}.{column_name}"
        assert column.type.asdecimal is True


def test_all_foreign_keys_are_restrict():
    foreign_keys = [
        fk
        for table in Base.metadata.tables.values()
        for fk in table.foreign_key_constraints
    ]
    assert len(foreign_keys) == 33
    assert all(fk.ondelete == "RESTRICT" for fk in foreign_keys)


def test_all_expected_checks_and_uniques_are_present():
    checks = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    uniques = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert len(checks) == 75
    assert len(uniques) == 14
    assert all(constraint.name for constraint in checks)
    assert all(constraint.name for constraint in uniques)


def test_search_vector_is_generated():
    search_vector = Base.metadata.tables["normative_chunks"].c.search_vector
    assert search_vector.computed is not None
    assert "to_tsvector" in str(search_vector.computed.sqltext)


def test_uuid_primary_keys_have_database_defaults():
    single_pk_tables = [
        table
        for table in Base.metadata.tables.values()
        if len(table.primary_key.columns) == 1
    ]
    assert len(single_pk_tables) == 17

    for table in single_pk_tables:
        pk_column = next(iter(table.primary_key.columns))
        assert pk_column.server_default is not None, table.name
        assert "gen_random_uuid()" in str(pk_column.server_default.arg), table.name


def test_key_server_defaults_match_ddl():
    expected = {
        ("users", "role"): "'operator'",
        ("users", "is_active"): "true",
        ("buildings", "additional_properties"): "'{}'::jsonb",
        ("rates", "rate_unit_multiplier"): "1",
        ("norm_sources", "is_current"): "true",
        ("estimates", "currency"): "'RUB'",
        ("estimate_items", "coefficient"): "1",
        ("normative_chunks", "metadata"): "'{}'::jsonb",
        ("audit_events", "changes"): "'{}'::jsonb",
        ("repair_requests", "status"): "'created'",
        ("defects", "confirmation_status"): "'suggested'",
    }
    for (table_name, column_name), default in expected.items():
        column = Base.metadata.tables[table_name].c[column_name]
        assert column.server_default is not None, f"{table_name}.{column_name}"
        assert str(column.server_default.arg) == default


def test_money_values_are_decimal_in_python_annotations():
    # Проверяем аннотации, чтобы ORM не возвращал float для денег/объёмов.
    for table_name, column_name in DECIMAL_COLUMNS:
        column = Base.metadata.tables[table_name].c[column_name]
        annotation = column.type.python_type
        assert annotation is Decimal, f"{table_name}.{column_name} -> {annotation}"
