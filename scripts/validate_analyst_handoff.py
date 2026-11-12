"""Validate received analyst artifacts, not application or ML acceptance.

Run from the repository root: python -B scripts/validate_analyst_handoff.py
Optionally supply --archive PATH to verify the original ZIP as well.
Requires Pillow for actual JPEG decoding; no network or database is used.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/analysis/nastya-2026-11-04"
ARCHIVE_SHA256 = "d391201e1607ac46e1cdba7ad9b34d17436b72a98642574f8f8ff7d20161ebd9"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def safe_relative(value):
    require(isinstance(value, str), "Expected relative path string")
    path = PurePosixPath(value)
    require(bool(path.parts) and not path.is_absolute() and ".." not in path.parts
            and "\\" not in value and ":" not in value, f"Unsafe source path: {value}")
    return path


def validate_handoff(archive=None):
    from PIL import Image

    provenance = read_json(PACKAGE / "provenance.json")
    require(provenance["archive_sha256"] == ARCHIVE_SHA256, "Unexpected source archive")
    require(provenance["target_branch"] == "dev" and provenance["source_modified"] is False,
            "Handoff must preserve the received source on dev")
    source = PACKAGE / "source"
    expected = {}
    json_count = photo_count = markdown_count = 0
    for entry in provenance["files"]:
        relative = safe_relative(entry["archive_path"])
        require(relative.as_posix() not in expected, f"Duplicate source: {relative}")
        target = source.joinpath(*relative.parts)
        require(target.resolve().is_relative_to(source.resolve()), f"Escaped source: {relative}")
        require(target.relative_to(ROOT).as_posix() == entry["repository_path"],
                f"Incorrect repository mapping: {relative}")
        data = target.read_bytes()
        require(len(data) == entry["size_bytes"], f"Size changed: {relative}")
        require(hashlib.sha256(data).hexdigest() == entry["sha256"], f"SHA256 changed: {relative}")
        expected[relative.as_posix()] = entry
        if target.suffix == ".json":
            read_json(target)
            json_count += 1
        elif target.suffix == ".md":
            require("\ufffd" not in data.decode("utf-8-sig"), f"Invalid source text: {relative}")
            markdown_count += 1
        elif target.suffix == ".jpg":
            with Image.open(io.BytesIO(data)) as photo:
                require(photo.format == "JPEG", f"Incorrect photo format: {relative}")
                photo.verify()
            with Image.open(io.BytesIO(data)) as photo:
                photo.load()
                require(photo.width > 0 and photo.height > 0, f"Empty photo: {relative}")
            photo_count += 1
        else:
            raise AssertionError(f"Unexpected source type: {relative}")
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    require(actual == set(expected), "Incomplete source inventory or unexpected files")
    require((len(expected), markdown_count, json_count, photo_count) == (31, 10, 7, 14),
            "Unexpected analyst package composition")

    cover = (source / "HANDOFF_README.md").read_text(encoding="utf-8-sig")
    checksums = re.findall(r"- `([^`]+)` \u2014 SHA256 `([0-9a-f]{64})`", cover)
    require(len(checksums) == 30 and len({p for p, _ in checksums}) == 30,
            "Incomplete original checksum list")
    for name, digest in checksums:
        require(name in expected and expected[name]["sha256"] == digest,
                f"Original cover checksum mismatch: {name}")

    evidence = read_json(source / "tests/fixtures/evidence_manifest.json")
    require(evidence["manifest_version"] == "1.2", "Unexpected evidence manifest version")
    cases = evidence["evidence_cases"]
    ids = [case["case_id"] for case in cases]
    require(len(ids) == 9 and set(ids) == {f"CASE-{i:02}" for i in range(1, 7)}
            | {f"CASE-NEG-{i:02}" for i in range(1, 4)}, "Incorrect evidence cases")
    photos = set()
    for case in cases:
        require(case["expected_test_metrics"]["is_executed"] is False,
                f"Source expectations must not become measured results: {case['case_id']}")
        for key in ("photo_before_path", "photo_after_path"):
            relative = safe_relative(case[key]).as_posix()
            require(relative in expected and relative.startswith("tests/fixtures/photos/")
                    and relative.endswith(".jpg"), f"Missing evidence photo: {relative}")
            photos.add(relative)
    require(len(photos) == 14, "Expected 14 unique referenced JPEGs")
    require(set(photos) == {p for p in expected if p.endswith(".jpg")}, "Unreferenced source photo")
    operations = read_json(source / "docs/domain/examples/maintenance_operations.json")["maintenance_operations"]
    require([o["operation_id"] for o in operations] == [f"1.{i}" for i in range(1, 7)],
            "Missing source operations")
    require(next(o for o in operations if o["operation_id"] == "1.4")["required_workers"] == 2,
            "Operation 1.4 requires two workers")
    calendars = read_json(source / "docs/domain/examples/maintenance_cases.json")["test_fixtures"]
    require([c["test_id"] for c in calendars] == [f"TC-{i:02}" for i in range(1, 6)],
            "Missing received calendar scenarios")

    if archive is not None:
        archive = Path(archive)
        require(archive.stat().st_size == provenance["archive_size_bytes"], "ZIP size mismatch")
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA256, "ZIP SHA256 mismatch")
        with ZipFile(archive) as zipped:
            require(zipped.testzip() is None, "ZIP CRC failure")
            entries = [info.filename for info in zipped.infolist() if not info.is_dir()]
            require(len(entries) == len(expected) and set(entries) == set(expected), "ZIP inventory mismatch")
            for name in entries:
                require(hashlib.sha256(zipped.read(name)).hexdigest() == expected[name]["sha256"],
                        f"ZIP entry mismatch: {name}")
    return {"files": len(expected), "markdown": markdown_count, "json": json_count,
            "jpeg": photo_count, "calendar_cases": len(calendars), "evidence_cases": len(cases),
            "photo_references": 2 * len(cases), "archive_checked": archive is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    result = validate_handoff(args.archive)
    print("PASS analyst handoff:", json.dumps(result, sort_keys=True))
    print("Source integrity only. No API/DB/ML execution or AN06/AN07 acceptance is claimed.")


if __name__ == "__main__":
    main()
