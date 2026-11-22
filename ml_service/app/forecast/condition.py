"""Condition evidence contract; no trained customer predictor is available yet.

NOTE on ALG07 vs ML RUL:
- ALG07 (FRAI-75): The deterministic regulatory schedule calculation based on equipment
  passport and manufacturer interval is owned and executed by the backend planning integration
  (`backend/app/integration/forecasting.py` and `scripts/verify_orchestration.py`).
- This ML module strictly enforces the No-Go policy for speculative ML-based RUL predictions
  at the MVP stage due to the verified deficit of historical failure data, returning status
  'insufficient_data' or 'unavailable' (MODEL_NOT_READY) and NEVER returning an ungrounded date.
"""
from datetime import date, datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_at: AwareDatetime
    description: str = Field(min_length=1)
    severity: Literal["unknown", "normal", "warning", "critical"] = "unknown"


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    observed_at: AwareDatetime
    name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)


class ConditionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    data_origin: Literal["customer", "synthetic_demo"]
    equipment_id: str = Field(min_length=1)
    as_of: AwareDatetime
    maintenance_history: list[Evidence] = Field(default_factory=list)
    remarks: list[Evidence] = Field(default_factory=list)
    runtime_hours: float | None = Field(default=None, ge=0)
    measurements: list[Measurement] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_future_evidence(self):
        if any(e.observed_at > self.as_of for e in [*self.maintenance_history, *self.remarks, *self.measurements]):
            raise ValueError("Evidence cannot be later than as_of")
        return self


class DataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sufficient: bool
    available: list[str]
    missing: list[str]
    limitations: list[str]


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "insufficient_data", "unavailable", "failed"]
    suggested_date: date | None = None
    risk_level: Literal["unknown", "low", "medium", "high"] = "unknown"
    rationale: str
    data_quality: DataQuality
    model_version: str | None = None
    uncertainty: str
    error: str | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "ok" and (self.suggested_date is None or not self.model_version or self.error):
            raise ValueError("ok requires a date, model version and no error")
        if self.status != "ok" and (self.suggested_date is not None or not self.error):
            raise ValueError("non-ok requires no date and an error")
        return self


def assess_condition(request: ConditionRequest) -> Recommendation:
    """Describe available evidence, never pretend heuristic severity is a forecast."""
    fields = {"maintenance_history": bool(request.maintenance_history), "remarks": bool(request.remarks),
              "runtime_hours": request.runtime_hours is not None, "measurements": bool(request.measurements)}
    available = [name for name, present in fields.items() if present]
    missing = [name for name, present in fields.items() if not present]
    severity = {e.severity for e in request.remarks}
    risk = "high" if "critical" in severity else "medium" if "warning" in severity else "unknown"
    sufficient = bool(request.maintenance_history and (request.remarks or request.measurements) and request.runtime_hours is not None)
    return Recommendation(
        status="unavailable" if sufficient else "insufficient_data", risk_level=risk,
        rationale="Приоритет отражает только явно указанную критичность замечаний; обученного прогноза срока нет.",
        data_quality=DataQuality(sufficient=sufficient, available=available, missing=missing,
            limitations=["Полнота полей не подтверждает качество, свежесть или пригодность данных для обучения."]),
        model_version=None, uncertainty="Вероятность и точность не оценены.",
        error="MODEL_NOT_READY" if sufficient else "INSUFFICIENT_DATA",
    )
