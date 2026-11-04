"""Validate extracted checklist drafts and source traceability; no application/ML run."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.schemas.management import ChecklistSetting

CATALOG = ROOT / "docs/analysis/checklists/catalog.json"
SOURCE_ROOT = ROOT / "docs/analysis/nastya-2026-11-04/source"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_catalog():
    catalog = json.loads(CATALOG.read_bytes())
    require(catalog["schema_version"] == "analyst-checklists-1", "Unexpected catalog format")
    require(catalog["status"] == "draft_for_review", "Extraction must not imply regulatory approval")
    require(catalog["source_archive_sha256"] == "d391201e1607ac46e1cdba7ad9b34d17436b72a98642574f8f8ff7d20161ebd9",
            "Unexpected analyst archive")
    origins = {"source_requirement", "derived_field", "proposed_field"}
    require(set(catalog["origin_labels"]) == origins, "Missing origin explanations")
    line_counts = {}
    for key, source in catalog["sources"].items():
        path = (ROOT / source["path"]).resolve()
        require(path.is_relative_to(SOURCE_ROOT.resolve()), "Source must belong to the original handoff")
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == source["sha256"], f"Changed source: {key}")
        line_counts[key] = len(data.decode("utf-8-sig").splitlines())

    def references(refs):
        require(bool(refs), "Every extracted point needs a source")
        for ref in refs:
            require(ref["source_id"] in line_counts, "Unknown source")
            require(1 <= ref["line_start"] <= ref["line_end"] <= line_counts[ref["source_id"]],
                    "Invalid source line range")

    profiles = catalog["profiles"]
    expected_codes = [f"1.{index}" for index in range(1, 7)]
    require([p["operation_code"] for p in profiles] == expected_codes, "Expected all six operations")
    operations = json.loads((SOURCE_ROOT / "docs/domain/examples/maintenance_operations.json").read_bytes())["maintenance_operations"]
    counts = Counter()
    for profile, operation in zip(profiles, operations, strict=True):
        require(profile["status"] == "draft_for_review", "Profile is not an approved instruction")
        require(profile["title"] == operation["name"], "Operation title differs from source")
        require(profile["required_workers_from_source"] == operation["required_workers"], "Source crew changed")
        references(profile["source_refs"])
        require(bool(profile["engineer_review"]) and bool(profile["open_questions"]), "Missing human review or applicability questions")
        items = profile["items"]
        require(1 <= len(items) <= 100, "Checklist exceeds current contract")
        require(len({item["item_key"] for item in items}) == len(items), "Duplicate checklist item")
        photo_items = 0
        for item in items:
            require(item["origin"] in origins, "Missing provenance classification")
            references(item["source_refs"])
            setting = ChecklistSetting.model_validate(item["setting"])
            if setting.photo_required:
                photo_items += 1
                require(setting.visual_verifiability != "not_verifiable", "Photo point must describe visible evidence")
            counts[item["origin"]] += 1
        require(photo_items > 0, "Expected a photo evidence point for each documented operation")
    require(sum(counts.values()) == 46, "Incomplete extraction inventory")
    return dict(profiles=len(profiles), items=sum(counts.values()), origins=dict(counts), dto="ChecklistSetting", status=catalog["status"])


if __name__ == "__main__":
    print("PASS checklist drafts:", json.dumps(validate_catalog(), ensure_ascii=False, sort_keys=True))
    print("Source extraction and DTO validation only; no technological approval or runtime acceptance.")
