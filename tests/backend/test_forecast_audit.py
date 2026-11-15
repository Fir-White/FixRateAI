"""QA audit: two independent forecasts and the orchestrator policy.

The reference behavior is ``docs/service/planning.md`` (sections "Независимые
прогнозы и решение" and "Ограничение времени и восстановление"):

* both methods receive the same canonical snapshot, its ID/hash and the same
  mandatory due date;
* an unavailable/incorrect/out-of-window AI is a ``fallback`` to the confirmed
  rule, never a replacement of the rule;
* an earlier AI date is accepted on customer data only with a calibrated
  interval whose upper bound is before the rule date; ``unknown`` uncertainty
  and tree dispersion are not such evidence;
* for ``synthetic_demo`` an earlier in-window date is allowed with an explicit
  explanation that the model accuracy on the customer is not established;
* mismatched identities, a passed deadline and a rule date outside the window
  require manual review.

The tests never import ``ml_service`` as a forecasting implementation; they use
the pure orchestrator functions and a fixed snapshot hash, exactly as the
existing ``tests/backend/test_orchestration.py`` does.
"""
from datetime import date, datetime
from uuid import uuid4

import pytest

from app.orchestrator import decide
from app.orchestrator.forecast import algorithmic_forecast, bounded_ai, forecast_result
from app.schemas.maintenance import Uncertainty
from scripts.verify_orchestration import ai_value, inputs


def compare(snapshot, item, provider):
    run_id = uuid4()
    algorithmic = algorithmic_forecast(snapshot, item, run_id)
    ai = bounded_ai(snapshot, run_id, provider)
    return algorithmic, ai, decide(snapshot, algorithmic, ai)


def test_both_forecasts_share_snapshot_hash_run_and_due_date_without_mutation():
    snapshot, item = inputs()
    before = snapshot.model_dump_json()
    algorithmic, ai, decision = compare(snapshot, item, lambda value: ai_value(value))
    assert snapshot.model_dump_json() == before
    assert algorithmic.run_id == ai.run_id == decision.run_id
    assert algorithmic.snapshot_id == ai.snapshot_id == decision.snapshot_id == snapshot.snapshot_id
    assert algorithmic.snapshot_sha256 == ai.snapshot_sha256 == snapshot.content_sha256
    assert algorithmic.mandatory_due_date == ai.mandatory_due_date == snapshot.mandatory_due_date
    assert algorithmic.result_id != ai.result_id
    assert decision.algorithmic_result_id == algorithmic.result_id
    assert decision.ai_result_id == ai.result_id


def test_ai_unavailable_and_low_confidence_fall_back_to_the_confirmed_rule():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    for provider in (
        lambda value: forecast_result(value, uuid4(), "ai", status="unavailable",
                                      error="MODEL_NOT_READY", explanation="Модель отсутствует"),
        lambda value: forecast_result(value, uuid4(), "ai", status="needs_input",
                                      error="MODEL_LOW_CONFIDENCE", explanation="Низкая уверенность"),
    ):
        ai = bounded_ai(snapshot, algorithmic.run_id, provider)
        decision = decide(snapshot, algorithmic, ai)
        assert decision.status == "fallback"
        assert decision.selected_date == algorithmic.recommended_date == date(2026, 11, 10)
        assert decision.selected_date <= snapshot.mandatory_due_date


def test_calibrated_early_ai_date_is_selected_on_customer_data():
    snapshot, item = inputs("customer")
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value, "2026-11-05", calibrated=True))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "selected"
    assert decision.selected_date == date(2026, 11, 5)
    assert decision.reasons[0].startswith("AI_EARLY_EVIDENCE")


def test_uncalibrated_early_ai_date_falls_back_on_customer_data():
    snapshot, item = inputs("customer")
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value, "2026-11-05"))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "fallback"
    assert decision.selected_date == date(2026, 11, 10)
    assert decision.reasons[0].startswith("AI_EARLY_UNSUPPORTED")


def test_ai_after_the_mandatory_due_date_is_kept_but_not_selected():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value, "2026-11-12"))
    decision = decide(snapshot, algorithmic, ai)
    assert ai.status == "ok" and ai.recommended_date == date(2026, 11, 12)
    assert decision.status == "fallback"
    assert decision.selected_date == date(2026, 11, 10)
    assert decision.reasons[0].startswith("AI_AFTER_DEADLINE")


def test_ai_before_the_window_is_not_selected():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value, "2026-10-30"))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "fallback"
    assert decision.selected_date == date(2026, 11, 10)
    assert decision.reasons[0].startswith("AI_BEFORE_WINDOW")


def test_foreign_snapshot_identity_is_a_terminal_ai_failure():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id,
                    lambda value: ai_value(value).model_copy(update={"snapshot_id": uuid4()}))
    assert ai.status == "failed" and ai.error_code == "AI_SNAPSHOT_MISMATCH"
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "fallback" and decision.selected_date == date(2026, 11, 10)


def test_ai_cannot_replace_the_mandatory_due_date():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id,
                    lambda value: ai_value(value).model_copy(
                        update={"mandatory_due_date": date(2026, 11, 9)}))
    assert ai.status == "failed" and ai.error_code == "AI_SNAPSHOT_MISMATCH"


def test_snapshot_hash_is_rechecked_before_any_calculation():
    from app.orchestrator.forecast import compare_forecasts

    snapshot, item = inputs()
    tampered = snapshot.model_copy(update={"content_sha256": "1" * 64})
    with pytest.raises(ValueError, match="hash"):
        compare_forecasts(tampered, item, lambda value: ai_value(value))


def test_synthetic_demo_early_date_is_selected_with_an_explicit_demo_reason():
    snapshot, item = inputs("synthetic_demo")
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value, "2026-11-05"))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "selected"
    assert decision.selected_date == date(2026, 11, 5)
    assert decision.reasons[0].startswith("DEMO_EARLY_DATE")


def test_missing_confirmed_rule_requires_input_and_ai_cannot_replace_it():
    snapshot, item = inputs()
    rule = item.rule.model_copy(update={"confirmed": False})
    item = item.model_copy(update={"rule": rule})
    snapshot = snapshot.model_copy(update={"rule": rule})
    from ml_service.app.forecast.synthetic import compute_snapshot_hash
    import json
    snapshot = snapshot.model_copy(
        update={"content_sha256": compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value))
    decision = decide(snapshot, algorithmic, ai)
    assert algorithmic.status == "needs_input"
    assert decision.status == "needs_input" and decision.selected_date is None


def test_passed_deadline_requires_manual_review_even_with_a_valid_ai_date():
    snapshot, item = inputs()
    snapshot = snapshot.model_copy(
        update={"as_of": datetime.fromisoformat("2026-11-11T08:00:00+05:00")})
    from ml_service.app.forecast.synthetic import compute_snapshot_hash
    import json
    snapshot = snapshot.model_copy(
        update={"content_sha256": compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "manual_review"
    assert decision.selected_date is None
    assert decision.reasons[0].startswith("DEADLINE_EXCEEDED")


def test_mismatched_result_identity_requires_manual_review():
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id, lambda value: ai_value(value))
    foreign = ai.model_copy(update={"snapshot_id": uuid4()})
    decision = decide(snapshot, algorithmic, foreign)
    assert decision.status == "manual_review"
    assert decision.selected_date is None
    assert decision.reasons[0].startswith("SNAPSHOT_MISMATCH")


@pytest.mark.xfail(strict=True, reason="BUG-01: unknown uncertainty with calibrated=True is accepted as early evidence")
def test_unknown_uncertainty_is_not_early_evidence():
    # docs/service/planning.md: "Неизвестная уверенность ... такой оценкой не являются."
    snapshot, item = inputs("customer")
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())

    def unknown(value):
        return ai_value(value, "2026-11-05").model_copy(update={"uncertainty": Uncertainty(
            kind="unknown", lower_date=date(2026, 11, 5), upper_date=date(2026, 11, 5),
            calibrated=True, note="Заявленная, но неизвестная уверенность")})

    ai = bounded_ai(snapshot, algorithmic.run_id, unknown)
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "fallback"
    assert decision.selected_date == date(2026, 11, 10)


@pytest.mark.xfail(strict=True, reason="BUG-02: a tampered earlier algorithmic date is trusted as the fallback")
def test_tampered_earlier_algorithmic_date_is_not_trusted():
    # The algorithmic result must come from ALG02 for this snapshot.  A date
    # that is inside the window but earlier than the real regulation date must
    # not silently replace it when AI is unavailable.
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    tampered = algorithmic.model_copy(update={"recommended_date": date(2026, 11, 5)})
    ai = bounded_ai(snapshot, algorithmic.run_id,
                    lambda value: forecast_result(value, uuid4(), "ai", status="unavailable",
                                                  error="MODEL_NOT_READY", explanation="Модель отсутствует"))
    decision = decide(snapshot, tampered, ai)
    assert decision.selected_date == algorithmic.recommended_date == date(2026, 11, 10)


@pytest.mark.xfail(strict=True, reason="BUG-03: bounded_ai trusts the AI-provided overdue flag")
def test_ai_overdue_flag_is_recomputed_from_the_snapshot():
    # A future due date (2026-11-10) with as_of 2026-11-01 cannot be overdue.
    snapshot, item = inputs()
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id,
                    lambda value: ai_value(value).model_copy(update={"overdue": True}))
    assert ai.overdue is False


@pytest.mark.xfail(strict=True, reason="BUG-05: synthetic_demo early date is rejected when AI reports unknown uncertainty")
def test_synthetic_demo_early_date_is_allowed_with_unknown_uncertainty():
    # docs/service/planning.md: for synthetic_demo an earlier in-window date is
    # allowed with an explicit demonstration explanation.  The default AI
    # result carries kind="unknown", which currently disables the demo branch.
    snapshot, item = inputs("synthetic_demo")
    algorithmic = algorithmic_forecast(snapshot, item, uuid4())
    ai = bounded_ai(snapshot, algorithmic.run_id,
                    lambda value: forecast_result(value, uuid4(), "ai", status="ok",
                                                  day=date(2026, 11, 5),
                                                  explanation="Синтетический ответ",
                                                  model_ref="synthetic_demo:fixture-v1"))
    decision = decide(snapshot, algorithmic, ai)
    assert decision.status == "selected"
    assert decision.selected_date == date(2026, 11, 5)
