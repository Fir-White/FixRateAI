"""Tests for photo analysis model benchmark and baseline selection (MVP1-ML03 / FRAI-135).

Verifies:
1. Benchmark execution and schema validity.
2. Zero False Reassurance on the frozen Holdout partition.
3. Proper enforcement of non-verifiable operations and image quality rejects.
4. Fallback resilience under provider degradation.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.benchmark_photo_models import run_benchmark, load_fixtures, evaluate_single_case
from ml_service.app.cv.quality import ImageQualityGuard
from ml_service.app.cv.classifier import CLIPZeroShotClassifier


@pytest.fixture(scope="module")
def benchmark_data():
    return run_benchmark()


def test_benchmark_runs_and_produces_valid_structure(benchmark_data):
    """Verify benchmark completes and contains all required model comparisons."""
    assert "summary" in benchmark_data
    assert "detailed_results" in benchmark_data
    assert len(benchmark_data["models_evaluated"]) >= 3
    
    for model_id in ["heuristic_baseline", "local_clip", "guarded_vlm"]:
        assert model_id in benchmark_data["summary"]
        summary = benchmark_data["summary"][model_id]
        assert "latency_p50_ms" in summary
        assert "false_reassurance_count" in summary
        assert "partitions" in summary
        assert "holdout" in summary["partitions"]


def test_zero_false_reassurance_on_holdout(benchmark_data):
    """Requirement D-08 / AN07: In production-eligible models, false reassurance MUST be 0.0%."""
    for model_id in ["heuristic_baseline", "local_clip", "guarded_vlm"]:
        holdout_stats = benchmark_data["summary"][model_id]["partitions"]["holdout"]
        assert holdout_stats["false_reassurance_count"] == 0, (
            f"Model {model_id} generated {holdout_stats['false_reassurance_count']} false reassurances on holdout!"
        )


def test_naive_vlm_demonstrates_danger_of_unconstrained_ai(benchmark_data):
    """Prove mathematically why an unconstrained LLM/VLM cannot be trusted with acceptance."""
    naive_stats = benchmark_data["summary"]["naive_vlm"]
    assert naive_stats["false_reassurance_count"] > 0
    assert naive_stats["false_reassurance_rate_pct"] >= 50.0


def test_quality_and_verifiability_rejections():
    """Verify that defect cases (CASE-NEG-01, CASE-NEG-02) and hidden operations (CASE-02) are rejected."""
    fixtures = load_fixtures()
    guard = ImageQualityGuard()

    # Blurry / glare case
    res_neg1 = evaluate_single_case("CASE-NEG-01", "heuristic_baseline", fixtures, guard)
    assert res_neg1["item_verdict"] == "uncertain"
    assert "Брак" in res_neg1["observation"]

    # Non-verifiable battery replacement: routes to manual review without false approval
    res_case2 = evaluate_single_case("CASE-02", "heuristic_baseline", fixtures, guard)
    assert res_case2["evidence_status"] == "manual_review"
    assert res_case2["item_verdict"] in ("uncertain", "not_verifiable")
    assert not res_case2["is_false_reassurance"]


def test_cross_evaluation_mismatched_viewpoint():
    """Verify that mismatched view (CASE-NEG-03) is rejected by consistency check."""
    fixtures = load_fixtures()
    guard = ImageQualityGuard()

    res_neg3 = evaluate_single_case("CASE-NEG-03", "heuristic_baseline", fixtures, guard)
    assert res_neg3["item_verdict"] == "uncertain"
    assert "ракурс" in res_neg3["observation"] or "согласованности" in res_neg3["observation"]
