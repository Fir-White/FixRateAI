"""Deterministic synthetic dataset generator for maintenance forecasting (Dataset B: synthetic_demo)."""
from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5, NAMESPACE_DNS
from zoneinfo import ZoneInfo
import numpy as np

from ml_service.app.schemas import (
    AcceptedEvent,
    ChecklistItem,
    Equipment,
    ForecastSnapshot,
    OperationVersion,
    RecurrenceRule,
    RuntimeReading,
    Site,
)

DEMO_NAMESPACE = uuid5(NAMESPACE_DNS, "fixrate.ai.synthetic_demo")


def compute_snapshot_hash(snapshot_dict: dict) -> str:
    """Calculate canonical SHA-256 hash of a snapshot payload without content_sha256."""
    payload = {k: v for k, v in snapshot_dict.items() if k != "content_sha256"}
    canonical_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _make_uuid(name: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, name)


def create_demo_site() -> Site:
    return Site(
        schema_version="maintenance-0.1",
        data_origin="synthetic_demo",
        site_id=_make_uuid("site-itp-1"),
        name="Индивидуальный тепловой пункт ИТП-1 (Синтетический)",
        address="г. Екатеринбург, ул. Малышева, д. 101",
        timezone="Asia/Yekaterinburg",
    )


def create_demo_operation() -> OperationVersion:
    return OperationVersion(
        schema_version="maintenance-0.1",
        data_origin="synthetic_demo",
        operation_id=_make_uuid("op-1.4"),
        operation_version_id=_make_uuid("op-ver-1.4.1"),
        version=1,
        code="1.4",
        title="Чистка всех узлов и агрегатов системы",
        maintenance_type="ТО2",
        instructions="Выполнить механическую и химическую очистку поверхностей теплообменника и грязевика от накипи и шлама.",
        crew_size=2,
        raw_norm_value=Decimal("60.000"),
        norm_unit="person_hour",
        planning_duration_minutes=60,
        duration_basis="утверждённая норма пилота",
        qualification_ids=[_make_uuid("qual-locksmith-3")],
        checklist=[
            ChecklistItem(
                checklist_item_id=_make_uuid("item-1.4.1"),
                text="Очистка теплообменных пластин и фланцев",
                answer_kind="boolean",
                unit=None,
                required=True,
                visual_verifiability="visible",
                photo_required=True,
            ),
            ChecklistItem(
                checklist_item_id=_make_uuid("item-1.4.2"),
                text="Промывка фильтра грубой очистки (грязевика)",
                answer_kind="boolean",
                unit=None,
                required=True,
                visual_verifiability="visible",
                photo_required=True,
            ),
        ],
        status="approved",
        source_ref="synthetic_demo:op-1.4",
    )


def create_demo_rule() -> RecurrenceRule:
    return RecurrenceRule(
        schema_version="maintenance-0.1",
        data_origin="synthetic_demo",
        rule_version_id=_make_uuid("rule-5year-2026"),
        regulation_version_id=_make_uuid("reg-ver-1"),
        source_text="5/год (подтверждённые даты на 2026 год)",
        kind="explicit_dates",
        confirmed=True,
        interval=None,
        calendar_unit=None,
        anchor_date=None,
        basis=None,
        explicit_dates=[
            date(2026, 2, 15),
            date(2026, 4, 30),
            date(2026, 7, 15),
            date(2026, 9, 30),
            date(2026, 11, 1),
        ],
        yearly_count=5,
        runtime_interval_hours=None,
        allowed_lead_days=6,
        source_ref="synthetic_demo:rule-5year",
    )


def generate_synthetic_forecast_dataset(
    n_samples: int = 50,
    seed: int = 42,
) -> tuple[list[ForecastSnapshot], np.ndarray]:
    """Generate a reproducible synthetic training dataset of (snapshots, target_days).

    Target is the number of days from snapshot.as_of until actual observed need arose.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    site = create_demo_site()
    operation = create_demo_operation()
    rule = create_demo_rule()
    site_tz = ZoneInfo(site.timezone)

    equipment_list = [
        Equipment(
            schema_version="maintenance-0.1",
            data_origin="synthetic_demo",
            equipment_id=_make_uuid(f"eq-heat-exchanger-{i}"),
            site_id=site.site_id,
            equipment_type_id=_make_uuid(f"eq-type-heat-exchanger-{i % 2}"),
            inventory_code=f"ИТП-ТО-{100 + i}",
            name=f"Теплообменник пластинчатый контура отопления №{i + 1}",
            commissioned_on=date(2024, 1, 15) + timedelta(days=i * 60),
            state="active",
            revision=1,
        )
        for i in range(5)
    ]

    snapshots: list[ForecastSnapshot] = []
    targets: list[float] = []

    base_date = datetime(2026, 5, 1, 12, 0, 0, tzinfo=site_tz)

    for idx in range(n_samples):
        eq = rng.choice(equipment_list)
        # Advance time by index
        as_of_dt = base_date + timedelta(days=idx * 3, hours=rng.randint(0, 8))
        as_of_date = as_of_dt.date()

        horizon_end = as_of_date + timedelta(days=90)
        mandatory_due = as_of_date + timedelta(days=rng.randint(10, 45))
        earliest_date = mandatory_due - timedelta(days=rule.allowed_lead_days)

        # Generate 1 to 4 historical accepted events strictly BEFORE as_of
        n_events = rng.randint(1, 4)
        accepted_events: list[AcceptedEvent] = []
        cur_runtime = 500.0 + idx * 45.0

        for e_idx in range(n_events):
            days_ago = (n_events - e_idx) * rng.randint(25, 40)
            perf_dt = as_of_dt - timedelta(days=days_ago)
            accept_dt = perf_dt + timedelta(hours=rng.randint(1, 12))
            
            # Ensure accepted_at <= as_of
            if accept_dt > as_of_dt:
                accept_dt = as_of_dt - timedelta(minutes=10)
            if perf_dt > accept_dt:
                perf_dt = accept_dt - timedelta(hours=2)

            ev_runtime = cur_runtime - (n_events - e_idx) * 200.0
            accepted_events.append(
                AcceptedEvent(
                    service_event_id=_make_uuid(f"event-{idx}-{e_idx}"),
                    performed_at=perf_dt,
                    accepted_at=accept_dt,
                    runtime_hours=Decimal(f"{max(50.0, ev_runtime):.3f}"),
                    observed_need_date=perf_dt.date() - timedelta(days=1),
                )
            )

        reading = RuntimeReading(
            reading_id=_make_uuid(f"reading-{idx}"),
            measured_at=as_of_dt - timedelta(hours=rng.randint(1, 4)),
            value_hours=Decimal(f"{cur_runtime:.3f}"),
            meter_epoch=1,
            verified=True,
        )

        # Model actual target: days from as_of to observed need date
        # Target influenced by runtime delta and equipment age
        last_event_date = accepted_events[-1].performed_at.date()
        days_since_last = (as_of_date - last_event_date).days
        noise = float(np_rng.normal(0, 1.5))
        expected_interval = 35.0 - (cur_runtime % 100) * 0.05
        target_days = max(1.0, round(expected_interval - days_since_last + noise))

        raw_snapshot_data = {
            "schema_version": "maintenance-0.1",
            "data_origin": "synthetic_demo",
            "snapshot_id": str(_make_uuid(f"snapshot-{idx}")),
            "content_sha256": "0" * 64,  # placeholder before hash calculation
            "binding_id": str(_make_uuid(f"binding-{idx % 5}")),
            "binding_revision": 1,
            "site": site.model_dump(mode="json"),
            "equipment": eq.model_dump(mode="json"),
            "operation": operation.model_dump(mode="json"),
            "rule": rule.model_dump(mode="json"),
            "as_of": as_of_dt.isoformat(),
            "horizon_end": horizon_end.isoformat(),
            "earliest_date": earliest_date.isoformat(),
            "mandatory_due_date": mandatory_due.isoformat(),
            "runtime_due_at_hours": None,
            "accepted_events": [e.model_dump(mode="json") for e in accepted_events],
            "runtime_reading": reading.model_dump(mode="json"),
            "feature_schema_version": "rf-features-v1",
        }

        # Calculate exact canonical content hash
        computed_hash = compute_snapshot_hash(raw_snapshot_data)
        raw_snapshot_data["content_sha256"] = computed_hash

        snapshot = ForecastSnapshot.model_validate_json(json.dumps(raw_snapshot_data))
        snapshots.append(snapshot)
        targets.append(float(target_days))

    return snapshots, np.array(targets, dtype=np.float64)
