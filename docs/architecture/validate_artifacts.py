"""Локальная проверка проектных артефактов; не интеграционные тесты приложения.

Зависимости: Python >=3.11, Pydantic >=2.5,<3, tzdata для Windows.
Запуск из корня: python -B docs/architecture/validate_artifacts.py
Обновление экспортированной схемы: добавить --write-schema.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from pydantic.json_schema import models_json_schema

from contracts.maintenance_contracts import CONTRACTS

ROOT = Path(__file__).resolve().parent


def canonical_hash(payload):
    data = {k: v for k, v in payload.items() if k != "content_sha256"}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_forecast(result, snapshot):
    for key, expected in {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_sha256": snapshot.content_sha256,
        "equipment_id": snapshot.equipment.equipment_id,
        "binding_id": snapshot.binding_id,
        "as_of": snapshot.as_of,
        "data_origin": snapshot.data_origin,
        "mandatory_due_date": snapshot.mandatory_due_date,
        "runtime_due_at_hours": snapshot.runtime_due_at_hours,
    }.items():
        require(getattr(result, key) == expected, f"forecast mismatch: {key}")
    if result.recommended_date:
        require(result.recommended_date <= snapshot.horizon_end, "forecast beyond requested horizon")


def check_decision(decision, algorithmic, ai, snapshot):
    require(algorithmic.method == "algorithmic" and ai.method == "ai", "wrong forecast methods")
    require(algorithmic.run_id == ai.run_id == decision.run_id, "different comparison runs")
    require(decision.snapshot_id == snapshot.snapshot_id, "decision snapshot mismatch")
    require(decision.algorithmic_result_id == algorithmic.result_id, "algorithmic reference mismatch")
    require(decision.ai_result_id == ai.result_id, "ai reference mismatch")
    require(decision.data_origin == snapshot.data_origin, "decision provenance mismatch")
    if decision.selected_date:
        local_day = snapshot.as_of.astimezone(ZoneInfo(snapshot.site.timezone)).date()
        require(snapshot.mandatory_due_date is not None, "cannot select without mandatory calendar bound")
        require(local_day <= decision.selected_date <= snapshot.mandatory_due_date, "selected date violates mandatory deadline")
        if snapshot.earliest_date:
            require(decision.selected_date >= snapshot.earliest_date, "selected date before allowed window")
        require(algorithmic.status == "ok", "cannot select without valid algorithmic result")
    if decision.status == "fallback":
        require(ai.status != "ok", "fallback requires unsuccessful ai result")
    if decision.status == "selected":
        require(ai.status == algorithmic.status == "ok", "selected requires two valid results")


def validate_models(examples):
    parsed = {}
    for entry in examples:
        name, contract, payload = entry["name"], entry["contract"], entry["payload"]
        require(name not in parsed, f"duplicate example name: {name}")
        parsed[name] = CONTRACTS[contract].model_validate_json(json.dumps(payload, ensure_ascii=False))
    return parsed


def check_relations(parsed, examples):
    snapshot = parsed["forecast_snapshot"]
    require(snapshot.content_sha256 == canonical_hash(next(x["payload"] for x in examples if x["name"] == "forecast_snapshot")), "snapshot hash mismatch")
    forecasts = [v for v in parsed.values() if type(v).__name__ == "ForecastResult"]
    for result in forecasts:
        check_forecast(result, snapshot)
    decisions = [v for v in parsed.values() if type(v).__name__ == "OrchestrationDecision"]
    for decision in decisions:
        group = [v for v in forecasts if v.run_id == decision.run_id]
        require(len(group) == 2, "comparison needs exactly two forecasts")
        check_decision(decision, next(x for x in group if x.method == "algorithmic"), next(x for x in group if x.method == "ai"), snapshot)
    task, execution, operation = parsed["task"], parsed["execution_report"], parsed["operation"]
    occurrence = parsed["schedule"].occurrences[0]
    require(task.task_id == occurrence.task_id and task.occurrence_id == occurrence.occurrence_id, "task/occurrence mismatch")
    require(task.operation_version_id == operation.operation_version_id == occurrence.operation_version_id, "operation version mismatch")
    require(task.equipment_id == snapshot.equipment.equipment_id, "task equipment mismatch")
    require(task.active_execution_id == execution.execution_id and task.task_id == execution.task_id, "execution mismatch")
    assignments = [v for v in parsed.values() if type(v).__name__ == "Assignment"]
    require(len(assignments) == operation.crew_size, "incomplete example crew")
    require({a.assignment_id for a in assignments} == set(task.assignment_ids), "assignment references mismatch")
    for assignment in assignments:
        require(assignment.task_id == task.task_id, "assignment task mismatch")
        require(assignment.start_at == task.scheduled_start and assignment.end_at == task.scheduled_end, "crew interval mismatch")
        require(set(operation.qualification_ids) <= set(assignment.qualification_ids), "qualification mismatch")
    require((task.scheduled_end-task.scheduled_start).total_seconds() == operation.planning_duration_minutes*60, "duration mismatch")
    require(execution.submitted_by in {a.executor_id for a in assignments}, "report author not assigned")
    require(parsed["engineer_decision"].engineer_id not in {a.executor_id for a in assignments}, "self acceptance")
    require({a.checklist_item_id for a in execution.answers} == {c.checklist_item_id for c in operation.checklist}, "checklist version mismatch")
    photos = [parsed["photo_before"], parsed["photo_after"]]
    require(set(execution.photo_ids) == {p.photo_id for p in photos}, "report photo references mismatch")
    require(photos[0].view_key == photos[1].view_key, "photo view mismatch")
    require(photos[0].uploaded_at <= execution.answers[0].completed_at <= photos[1].uploaded_at <= execution.submitted_at, "photo/checklist timeline mismatch")
    require(parsed["photo_review_request"].report == execution, "review report snapshot mismatch")
    review, decision = parsed["photo_review_result"], parsed["engineer_decision"]
    require(review.execution_id == decision.execution_id == execution.execution_id, "review/decision execution mismatch")
    require(decision.reviewed_ai_result_id == review.ai_review_id, "engineer reviewed another ai result")
    require(execution.submitted_at <= review.created_at <= decision.decided_at, "review/decision timeline mismatch")
    require(set(review.input_photo_ids) == set(execution.photo_ids), "ai reviewed other photos")
    return len(decisions)


def negative_checks(parsed, examples):
    payloads = {x["name"]: x["payload"] for x in examples}
    rejected = 0

    def reject(contract, original, mutate):
        nonlocal rejected
        payload = deepcopy(payloads[original])
        mutate(payload)
        try:
            CONTRACTS[contract].model_validate_json(json.dumps(payload, ensure_ascii=False))
        except (ValidationError, ValueError):
            rejected += 1
            return
        raise AssertionError(f"invalid {original} unexpectedly accepted")

    reject("ForecastResult", "ai_forecast", lambda p: p.update(predicted_date="2026-10-29"))
    reject("ForecastResult", "ai_forecast", lambda p: p.update(recommended_date=None))
    reject("ForecastResult", "ai_unavailable", lambda p: p.update(recommended_date="2026-10-29"))
    reject("ForecastResult", "ai_forecast", lambda p: p.update(as_of="2026-10-26T12:00:00"))
    reject("ForecastSnapshot", "forecast_snapshot", lambda p: p["accepted_events"][0].update(accepted_at="2027-01-01T00:00:00+05:00"))
    reject("ForecastSnapshot", "forecast_snapshot", lambda p: p["equipment"].update(data_origin="customer"))
    reject("RecurrenceRule", "recurrence_rule", lambda p: p["explicit_dates"].pop())
    reject("PhotoReviewRequest", "photo_review_request", lambda p: p["photos"][0].update(execution_id="00000000-0000-4000-8000-000000000999"))
    require(rejected == 8, "missing negative shape check")
    wrong = parsed["ai_forecast"].model_copy(update={"snapshot_sha256": "0"*64})
    try:
        check_forecast(wrong, parsed["forecast_snapshot"])
    except AssertionError:
        rejected += 1
    else:
        raise AssertionError("foreign snapshot unexpectedly accepted")
    from datetime import date
    wrong_decision = parsed["orchestration_decision"].model_copy(update={"selected_date": date(2026, 11, 2)})
    try:
        check_decision(wrong_decision, parsed["algorithmic_forecast"], parsed["ai_forecast"], parsed["forecast_snapshot"])
    except AssertionError:
        rejected += 1
    else:
        raise AssertionError("late selected date unexpectedly accepted")
    return rejected


def check_documents():
    count = 0
    for path in ROOT.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        require("\ufffd" not in content, f"encoding replacement character: {path}")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            if re.match(r"^[a-z]+://", target) or target.startswith("#"):
                continue
            target = target.split("#")[0]
            require((path.parent / target).exists(), f"broken link: {path.name} -> {target}")
            count += 1
    mermaid = (ROOT / "diagrams/system_architecture.mmd").read_text(encoding="utf-8").strip()
    embedded = re.search(r"```mermaid\n(.*?)\n```", (ROOT/"system_architecture.md").read_text(encoding="utf-8"), re.S).group(1).strip()
    require(embedded == mermaid, "embedded/source Mermaid differ")
    drawing = ET.parse(ROOT / "diagrams/system_architecture.drawio")
    cells = drawing.findall(".//mxCell")
    ids = {c.get("id") for c in cells}
    require(len(ids) == len(cells), "duplicate draw.io cell ID")
    edges = {(c.get("source"), c.get("target")) for c in cells if c.get("edge") == "1"}
    for source, target in edges:
        require(source in ids and target in ids, "draw.io dangling edge")
    mermaid_edges = set()
    for line in mermaid.splitlines():
        m = re.match(r"\s*(\w+)(?:\[.*?\])?\s*-->\s*(\w+)", line)
        if m:
            mermaid_edges.add(m.groups())
    require(edges == mermaid_edges, "draw.io/Mermaid edges differ")
    validation = (ROOT / "architecture_validation.md").read_text(encoding="utf-8")
    scenario_ids = re.findall(r"^\| (S\d{2}) \|", validation, re.M)
    require(scenario_ids == [f"S{i:02}" for i in range(1, 16)], "scenario matrix must contain S01..S15 exactly once")
    return count, len(edges)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-schema", action="store_true")
    args = parser.parse_args()
    _, generated = models_json_schema([(c, "validation") for c in CONTRACTS.values()])
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:fixrate:maintenance:0.1",
        "title": "FixRate maintenance-0.1 contract definitions",
        **generated,
    }
    schema_path = ROOT / "contracts/maintenance.schema.json"
    if args.write_schema:
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    require(json.loads(schema_path.read_text(encoding="utf-8")) == schema, "schema export differs; use --write-schema")
    examples = json.loads((ROOT/"contracts/examples.json").read_text(encoding="utf-8"))["examples"]
    parsed = validate_models(examples)
    comparisons = check_relations(parsed, examples)
    negatives = negative_checks(parsed, examples)
    links, edges = check_documents()
    print(f"OK: {len(examples)} JSON examples; {comparisons} comparison sets; {negatives} negative checks; schema matches; {links} local links; {edges} diagram edges; S01..S15 present.")
    print("This validates design artifacts only; application/API/DB/ML integration was not run.")


if __name__ == "__main__":
    main()
