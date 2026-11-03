"""Feature extraction for maintenance forecasting (schema rf-features-v1)."""
from __future__ import annotations

import hashlib
from datetime import date
from zoneinfo import ZoneInfo
import numpy as np

from ml_service.app.schemas import ForecastSnapshot

FEATURE_SCHEMA_VERSION = "rf-features-v1"
FEATURE_NAMES = [
    "eq_type_code",
    "age_days",
    "days_since_last_service",
    "runtime_hours_delta",
    "history_event_count",
    "mean_prior_interval_days",
]


class FeatureExtractor:
    """Extracts numeric feature vectors from ForecastSnapshot."""

    def __init__(self, schema_version: str = FEATURE_SCHEMA_VERSION):
        self.schema_version = schema_version

    def extract_features(self, snapshot: ForecastSnapshot) -> np.ndarray:
        """Extract a 1D numpy array of shape (6,) from a single snapshot."""
        # 1. Local date of as_of according to site timezone
        site_tz = ZoneInfo(snapshot.site.timezone)
        as_of_local = snapshot.as_of.astimezone(site_tz)
        as_of_date = as_of_local.date()

        # 2. Equipment type code (deterministic int in range [0, 999])
        eq_type_raw = str(snapshot.equipment.equipment_type_id).encode("utf-8")
        eq_type_code = float(int(hashlib.md5(eq_type_raw).hexdigest()[:4], 16) % 1000)

        # 3. Equipment age in days
        if snapshot.equipment.commissioned_on:
            age_days = float(max(0, (as_of_date - snapshot.equipment.commissioned_on).days))
        else:
            age_days = 365.0

        # 4. Accepted events analysis (guaranteed performed_at <= accepted_at <= as_of)
        valid_events = sorted(snapshot.accepted_events, key=lambda e: e.performed_at)
        history_event_count = float(len(valid_events))

        if valid_events:
            last_event = valid_events[-1]
            event_dates = [e.performed_at.astimezone(site_tz).date() for e in valid_events]
            last_event_date = event_dates[-1]
            days_since_last_service = float(max(0, (as_of_date - last_event_date).days))

            # Runtime hours delta since last service
            if snapshot.runtime_reading is not None and last_event.runtime_hours is not None:
                runtime_hours_delta = float(max(0.0, float(snapshot.runtime_reading.value_hours - last_event.runtime_hours)))
            elif snapshot.runtime_reading is not None:
                runtime_hours_delta = float(snapshot.runtime_reading.value_hours)
            else:
                runtime_hours_delta = 0.0

            # Mean prior interval in days
            if len(event_dates) >= 2:
                intervals = [max(1, (event_dates[i] - event_dates[i - 1]).days) for i in range(1, len(event_dates))]
                mean_prior_interval_days = float(sum(intervals) / len(intervals))
            else:
                mean_prior_interval_days = 30.0
        else:
            # Cold start: no accepted history
            days_since_last_service = age_days
            if snapshot.runtime_reading is not None:
                runtime_hours_delta = float(snapshot.runtime_reading.value_hours)
            else:
                runtime_hours_delta = 0.0
            mean_prior_interval_days = 30.0

        vector = np.array([
            eq_type_code,
            age_days,
            days_since_last_service,
            runtime_hours_delta,
            history_event_count,
            mean_prior_interval_days,
        ], dtype=np.float64)

        return vector

    def extract_batch(self, snapshots: list[ForecastSnapshot]) -> np.ndarray:
        """Extract a 2D numpy array of shape (N, 6) from a list of snapshots."""
        if not snapshots:
            return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)
        return np.array([self.extract_features(s) for s in snapshots], dtype=np.float64)
