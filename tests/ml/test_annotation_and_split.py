"""Test suite for expert annotation and dataset split leakage verification (MVP1-ML02 / FRAI-126)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.verify_split_leakage import verify_split

ROOT = Path(__file__).resolve().parents[2]
SPLIT_MANIFEST_PATH = ROOT / "data/manifests/split_manifest.json"
DATASET_MANIFEST_PATH = ROOT / "data/manifests/dataset_manifest.json"
ANNOTATION_MANIFEST_PATH = ROOT / "data/manifests/annotation_manifest.json"
POLICY_PATH = ROOT / "docs/analysis/photo_review_policy.json"


def test_annotation_manifest_valid():
    """Verify that annotation_manifest.json has all 9 cases and valid schema."""
    assert ANNOTATION_MANIFEST_PATH.exists()
    with open(ANNOTATION_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["schema_version"] == "1.0.0"
    assert data["protocol_version"] == "ann-proto-v1.0"
    assert len(data["cases"]) == 9

    case_ids = {c["case_id"] for c in data["cases"]}
    expected_cases = {
        "CASE-01",
        "CASE-02",
        "CASE-03",
        "CASE-04",
        "CASE-05",
        "CASE-06",
        "CASE-NEG-01",
        "CASE-NEG-02",
        "CASE-NEG-03",
    }
    assert case_ids == expected_cases


def test_split_manifest_zero_leakage():
    """Verify zero overlap between development and holdout partitions."""
    report = verify_split(
        split_manifest_path=SPLIT_MANIFEST_PATH,
        dataset_manifest_path=DATASET_MANIFEST_PATH,
        annotation_manifest_path=ANNOTATION_MANIFEST_PATH,
    )
    assert report["status"] == "PASS"
    assert len(report["errors"]) == 0
    assert report["equipment_overlap_count"] == 0
    assert report["hash_overlap_count"] == 0
    assert report["dev_cases_count"] == 4
    assert report["holdout_cases_count"] == 4


def test_uncertain_and_not_verifiable_are_allowed_verdicts():
    """Verify that not_verifiable and uncertain are valid first-class labels per guidelines."""
    with open(ANNOTATION_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    case_map = {c["case_id"]: c for c in data["cases"]}

    # CASE-06: Air release from closed pipe is physically not verifiable by optical photo
    assert case_map["CASE-06"]["visual_change_verdict"] == "not_verifiable"

    # CASE-NEG-01: Blurry glare photo has insufficient evidence
    assert case_map["CASE-NEG-01"]["visual_change_verdict"] == "uncertain"
    assert case_map["CASE-NEG-01"]["pair_comparability"]["comparability_verdict"] == "insufficient_evidence"


def test_policy_compliance_matches_photo_review_policy():
    """Verify that annotation manifest system verdicts match photo_review_policy.json."""
    with open(ANNOTATION_MANIFEST_PATH, "r", encoding="utf-8") as f:
        ann_data = json.load(f)
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        policy_data = json.load(f)

    policy_cases = policy_data["cases"]
    for case in ann_data["cases"]:
        cid = case["case_id"]
        assert cid in policy_cases, f"Case {cid} missing from policy"
        expected_allowed = policy_cases[cid]["allowed_classifications"]
        actual_allowed = case["policy_compliance"]["allowed_system_verdicts"]
        assert set(actual_allowed) == set(expected_allowed), f"Mismatch for {cid}"
