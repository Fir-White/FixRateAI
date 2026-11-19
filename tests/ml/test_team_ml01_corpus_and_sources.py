"""Tests for TEAM-ML01 deliverable: photo corpus, RAG source mapping, and resource forecast audit (FRAI-171).

Verifies:
1. RAG corpus manifest integrity and schema compliance (CR-17-05 / CR-17-06).
2. Referenced documentation files exist and have valid source revisions.
3. Negative and boundary RAG cases enforce anti-hallucination and ACL rules.
4. Contradiction handling on CASE-01 (dial mismatch) strictly prevents false approval.
5. Resource forecast audit confirms data deficiency and safeguards normative rule.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rag_manifest():
    manifest_path = ROOT / "data" / "manifests" / "rag_corpus_manifest.json"
    assert manifest_path.exists(), f"RAG corpus manifest not found at {manifest_path}"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def test_rag_corpus_manifest_structure(rag_manifest):
    """Verify that RAG corpus manifest adheres to CR-17 requirements."""
    assert rag_manifest["manifest_id"] == "frai-rag-corpus-v0.1.0"
    regime = rag_manifest["compliance_regime"]
    assert regime["cr_version"] == "CR-17"
    assert regime["active_business_roles"] == ["chief_engineer", "executor"]
    assert "PostgreSQL" in regime["source_of_truth"]
    assert len(rag_manifest["instruction_mapping"]) >= 5


def test_rag_corpus_documents_exist_and_valid(rag_manifest):
    """Verify all referenced corpus documents exist on disk with valid headers."""
    for entry in rag_manifest["instruction_mapping"]:
        source = entry["approved_source"]
        doc_path = ROOT / source["file_path"]
        assert doc_path.exists(), f"Corpus document missing: {doc_path}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content) > 100
        assert source["document_id"] in content
        assert source["source_revision"] in content
        assert "Ревизия" in content or "revision" in content.lower()


def test_rag_negative_and_boundary_cases(rag_manifest):
    """Verify presence of anti-hallucination and ACL boundary cases."""
    cases = rag_manifest["negative_and_boundary_cases"]
    case_ids = {c["case_id"] for c in cases}
    assert "RAG-NEG-01" in case_ids  # Missing document
    assert "RAG-NEG-02" in case_ids  # Cross-site ACL restriction
    assert "RAG-NEG-03" in case_ids  # Stale revision invalidation
    assert "RAG-NEG-04" in case_ids  # Prompt-injection in Excel

    for c in cases:
        assert "expected_behavior" in c
        assert "anti_hallucination_rule" in c


def test_case01_contradiction_yields_no_false_approval():
    """Verify that contradictory pair CASE-01 (different dials) never receives auto approval."""
    from scripts.benchmark_photo_models import load_fixtures, evaluate_single_case
    from ml_service.app.cv.quality import ImageQualityGuard

    fixtures = load_fixtures()
    guard = ImageQualityGuard()

    # Test under heuristic baseline
    res_heuristic = evaluate_single_case("CASE-01", "heuristic_baseline", fixtures, guard)
    assert res_heuristic["evidence_status"] != "approved"
    assert res_heuristic["evidence_status"] == "manual_review"
    assert not res_heuristic["is_false_reassurance"]

    # Test under guarded VLM
    res_guarded = evaluate_single_case("CASE-01", "guarded_vlm", fixtures, guard)
    assert res_guarded["evidence_status"] != "approved"
    assert res_guarded["item_verdict"] == "uncertain"
    assert not res_guarded["is_false_reassurance"]


def test_resource_forecast_audit_and_data_gap_assertion():
    """Verify ex-ML08 / FRAI-140: Absence of historical failures prevents ungrounded AI forecast."""
    from tests.fixtures.forecast_audit import inputs
    snapshot, item = inputs()

    # Real event history is empty in baseline fixtures
    assert snapshot.accepted_events == []
    assert snapshot.data_origin == "synthetic_demo"

    # Confirm that without failure events, snapshot does not claim real MTBF
    assert snapshot.runtime_due_at_hours is None
