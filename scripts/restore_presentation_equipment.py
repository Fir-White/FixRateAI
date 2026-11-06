"""Restore missing equipment links in the known fictional presentation site only.

Preview is the default. Apply requires an explicit site ID and DATABASE_URL.
No task, report, evidence, decision, schedule or existing relation is rewritten.
"""
import argparse
import hashlib
import json
import os
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import create_engine, text


def identity(key):
    return str(uuid5(NAMESPACE_URL, "fixrate:presentation:v1:" + key))


EXPECTED = {"1.1": "point", "1.2": "point", "1.3": "controller", "1.4": "pump", "1.5": "gauge", "1.6": "circuit"}
PROTECTED = ("work_orders", "work_reports", "acceptance_reviews", "evidence_files", "work_assignments", "schedule_entries", "work_readings", "forecast_runs", "ai_quality_checks", "orchestration_decisions")


def fingerprint(connection, site_id):
    result = {}
    for table in PROTECTED:
        # Table names are the constant whitelist above, never command-line input.
        rows = connection.execute(text(f"SELECT to_jsonb(t) FROM {table} t WHERE site_id=:site ORDER BY to_jsonb(t)::text"), {"site": site_id}).scalars().all()
        result[table] = {"rows": len(rows), "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}
    return result


def restore(engine, site_id, apply=False):
    if site_id != identity("site"):
        raise ValueError("Only the known presentation-v1 site is supported")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SELECT pg_advisory_xact_lock(6813061126)"))
            site = connection.execute(text("SELECT name FROM sites WHERE site_id=:site"), {"site": site_id}).scalar_one()
            before = fingerprint(connection, site_id)
            orders = connection.execute(text("SELECT * FROM work_orders WHERE site_id=:site ORDER BY work_order_id FOR UPDATE"), {"site": site_id}).mappings().all()
            pending, conflicts, existing, skipped = [], [], 0, []
            for order in orders:
                snapshot = order["operation_snapshot"]
                if snapshot.get("profile") != "presentation-v1" or snapshot.get("data_origin") != "synthetic_demo":
                    skipped.append(str(order["work_order_id"]))
                    continue
                code = snapshot.get("code")
                if code not in EXPECTED:
                    conflicts.append({"task": str(order["work_order_id"]), "reason": "unknown operation"})
                    continue
                candidates = connection.execute(text("""
                    SELECT DISTINCT e.equipment_id,e.system_id,e.asset_code,e.name,e.location,e.properties
                    FROM rule_equipment re JOIN equipment e USING(site_id,system_id,equipment_id)
                    WHERE re.site_id=:site AND re.system_id=:system AND re.maintenance_rule_id=:rule
                    AND (CAST(:entry AS uuid) IS NULL OR re.binding_id IN (
                        SELECT binding_id FROM schedule_entries WHERE schedule_entry_id=:entry
                        AND site_id=:site AND system_id=:system AND maintenance_rule_id=:rule))
                """), {"site": site_id, "system": order["system_id"], "rule": order["maintenance_rule_id"], "entry": order["schedule_entry_id"]}).mappings().all()
                if len(candidates) != 1 or str(candidates[0]["equipment_id"]) != identity(EXPECTED[code]) or candidates[0]["properties"].get("profile") != "presentation-v1" or candidates[0]["properties"].get("data_origin") != "synthetic_demo":
                    conflicts.append({"task": str(order["work_order_id"]), "reason": "equipment identity is not uniquely proven"})
                    continue
                equipment = candidates[0]
                links = connection.execute(text("SELECT equipment_id FROM work_order_equipment WHERE site_id=:site AND work_order_id=:task"), {"site": site_id, "task": order["work_order_id"]}).scalars().all()
                if links:
                    if len(links) == 1 and links[0] == equipment["equipment_id"]:
                        existing += 1
                    else:
                        conflicts.append({"task": str(order["work_order_id"]), "reason": "existing relation differs; no overwrite allowed"})
                    continue
                pending.append((order, equipment))
            if conflicts:
                raise RuntimeError(json.dumps({"conflicts": conflicts}, ensure_ascii=False))
            if apply:
                for order, equipment in pending:
                    provenance = "schedule_entry.binding_id" if order["schedule_entry_id"] else "maintenance_rule_id"
                    asset = dict(data_origin="synthetic_demo", profile="presentation-v1", asset_code=equipment["asset_code"], name=equipment["name"], location=equipment["location"], restored_from=provenance, repair="presentation-equipment-links-v1")
                    connection.execute(text("""INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id,asset_snapshot)
                        VALUES(:site,:system,:task,:equipment,CAST(:asset AS jsonb))"""), {"site": site_id, "system": order["system_id"], "task": order["work_order_id"], "equipment": equipment["equipment_id"], "asset": json.dumps(asset, ensure_ascii=False)})
                    after = dict(equipment_ids=[str(equipment["equipment_id"])], source=provenance, maintenance_rule_id=str(order["maintenance_rule_id"]), repair="presentation-equipment-links-v1", requested_by="local-demo-owner")
                    connection.execute(text("""INSERT INTO audit_events(site_id,actor_type,entity_type,entity_id,action,before_snapshot,after_snapshot)
                        VALUES(:site,'system','work_orders',:task,'restore_demo_equipment_link',CAST(:before AS jsonb),CAST(:after AS jsonb))"""), {"site": site_id, "task": order["work_order_id"], "before": '{"equipment_ids":[]}', "after": json.dumps(after)})
            after = fingerprint(connection, site_id)
            if before != after:
                raise RuntimeError("Protected facts changed; transaction rolled back")
            return dict(mode="applied" if apply else "preview", site_id=site_id, site=site, target_tasks=existing + len(pending), existing_links=existing, missing_links=len(pending), inserted=len(pending) if apply else 0, equipment_distribution=dict(Counter(equipment["name"] for _, equipment in pending)), skipped_non_presentation=skipped, protected_facts_unchanged=before == after, protected=after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        print(json.dumps(restore(engine, args.site_id, args.apply), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
