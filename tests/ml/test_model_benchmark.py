"""Tests for photo analysis model benchmark and baseline selection."""
from __future__ import annotations

import pytest

from scripts.benchmark_photo_models import run_benchmark, load_fixtures, evaluate_single_case
from ml_service.app.cv.quality import ImageQualityGuard


@pytest.fixture(scope="module")
def benchmark_data():
    return run_benchmark()


def test_benchmark_runs_and_produces_valid_structure(benchmark_data):
    assert "summary" in benchmark_data
    assert "detailed_results" in benchmark_data
    assert len(benchmark_data["models_evaluated"]) >= 2

    for model_id in ["aitunnel_unconfigured", "guarded_vlm"]:
        assert model_id in benchmark_data["summary"]
        summary = benchmark_data["summary"][model_id]
        assert "latency_p50_ms" in summary
        assert "false_reassurance_count" in summary
        assert "partitions" in summary
        assert "holdout" in summary["partitions"]


def test_zero_false_reassurance_on_holdout(benchmark_data):
    for model_id in ["aitunnel_unconfigured", "guarded_vlm"]:
        holdout_stats = benchmark_data["summary"][model_id]["partitions"]["holdout"]
        assert holdout_stats["false_reassurance_count"] == 0, (
            f"Model {model_id} generated {holdout_stats['false_reassurance_count']} false reassurances on holdout!"
        )


def test_naive_vlm_demonstrates_danger_of_unconstrained_ai(benchmark_data):
    naive_stats = benchmark_data["summary"]["naive_vlm"]
    assert naive_stats["false_reassurance_count"] > 0
    assert naive_stats["false_reassurance_rate_pct"] >= 50.0


def test_quality_and_verifiability_rejections(monkeypatch):
    monkeypatch.delenv("AITUNNEL_API_KEY", raising=False)
    monkeypatch.delenv("AI_TUNNEL_API_KEY", raising=False)
    fixtures = load_fixtures()
    guard = ImageQualityGuard()

    res_neg1 = evaluate_single_case("CASE-NEG-01", "aitunnel_unconfigured", fixtures, guard)
    assert res_neg1["item_verdict"] == "uncertain" and not res_neg1["is_false_reassurance"]

    res_case2 = evaluate_single_case("CASE-02", "aitunnel_unconfigured", fixtures, guard)
    assert res_case2["evidence_status"] == "manual_review"
    assert res_case2["item_verdict"] in ("uncertain", "not_verifiable")
    assert not res_case2["is_false_reassurance"]


def test_cross_evaluation_mismatched_viewpoint():
    fixtures = load_fixtures()
    guard = ImageQualityGuard()
    res_neg3 = evaluate_single_case("CASE-NEG-03", "aitunnel_unconfigured", fixtures, guard)
    assert res_neg3["item_verdict"] == "uncertain"
    assert not res_neg3["is_false_reassurance"]
