"""Offline mapper configuration smoke test; not a DDL compatibility test."""
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, MetaData, Numeric, String
from app.db import models


def test_all_mappers_configure_without_database(monkeypatch):
    catalog = json.loads((Path(__file__).resolve().parents[2] / "database/schema/model_catalog.json").read_text(encoding="utf-8"))

    def fake_reflect(metadata, bind, only):
        from sqlalchemy import Table
        for item in catalog["tables"]:
            columns = []
            for field in item["fields"]:
                kind = Numeric(13, 3) if item["name"] == "work_orders" and field["name"] == "norm_hours_snapshot" else String()
                columns.append(Column(field["name"], kind, primary_key=field["name"] in item["pk"]))
            if item["name"] in ("rule_equipment", "schedule_entries"):
                columns.append(Column("binding_id", String()))
            Table(item["name"], metadata, *columns)

    monkeypatch.setattr(MetaData, "reflect", fake_reflect)
    monkeypatch.setattr(models, "inspect", lambda engine: SimpleNamespace(has_table=lambda *args, **kwargs: False, get_foreign_keys=lambda *args, **kwargs: [
        {"name": "fk_work_orders_entry_rule", "constrained_columns": ["site_id", "system_id", "schedule_entry_id", "maintenance_rule_id"],
         "referred_table": "schedule_entries", "referred_columns": ["site_id", "system_id", "schedule_entry_id", "maintenance_rule_id"], "options": {"ondelete": "RESTRICT"}}
    ]))
    mapped = models.map_schema(SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    assert set(mapped.classes) == set(models.TABLES)
    assert mapped["work_orders"].__mapper__.relationships["entry"].viewonly
