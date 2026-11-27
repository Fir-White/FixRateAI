"""Test suite for photo dataset manifest and data provenance (MVP1-ML01 / FRAI-127)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.verify_photo_manifest import verify_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data/manifests/dataset_manifest.json"


def test_manifest_file_exists():
    """Verify that dataset_manifest.json exists and is readable."""
    assert MANIFEST_PATH.exists(), f"Manifest file missing at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema_version"] == "1.0.0"
    assert data["dataset_id"] == "frai-cv-v0.1.0-demo"
    assert len(data["items"]) == 14


def test_manifest_verification_passes():
    """Run programmatic verify_manifest and ensure PASS status."""
    report = verify_manifest(MANIFEST_PATH, check_hashes=True, check_exif=True)
    assert report["status"] == "PASS"
    assert len(report["errors"]) == 0
    assert report["verified_items"] == 14
    assert report["total_items"] == 14


def test_manifest_origins_partitioning():
    """Verify that all demo files are honestly partitioned and none are marked real_customer."""
    report = verify_manifest(MANIFEST_PATH, check_hashes=False, check_exif=False)
    origin_counts = report["origin_breakdown"]

    # 14 analyst handoff images: 9 demo, 3 synthetic_edited, 2 synthetic_augmented
    assert origin_counts.get("demo", 0) == 9
    assert origin_counts.get("synthetic_edited", 0) == 3
    assert origin_counts.get("synthetic_augmented", 0) == 2
    assert origin_counts.get("real_customer", 0) == 0

    # Ensure honest gap reporting
    assert report["real_customer_count"] == 0
    assert report["pilot_ready"] is False


def test_manifest_exif_safety_no_gps_leaks():
    """Verify that no image in the manifest contains GPS tags or sensitive device metadata."""
    report = verify_manifest(MANIFEST_PATH, check_hashes=False, check_exif=True)
    assert not any("GPS" in err for err in report["errors"])
    assert not any("PII" in err for err in report["errors"])
