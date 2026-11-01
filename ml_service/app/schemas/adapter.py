"""Schema adapter re-exporting canonical maintenance DTOs robustly."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _resolve_maintenance_module():
    # 1. Try if backend is already on PYTHONPATH and app.schemas.maintenance is valid
    try:
        import app.schemas.maintenance as mod
        if hasattr(mod, "ForecastSnapshot"):
            return mod
    except (ImportError, AttributeError):
        pass

    # 2. Try importing via backend.app.schemas.maintenance
    try:
        import backend.app.schemas.maintenance as mod
        if hasattr(mod, "ForecastSnapshot"):
            return mod
    except (ImportError, AttributeError):
        pass

    # 3. Direct file location fallback based on repository structure
    curr = Path(__file__).resolve()
    for parent in [curr.parent.parent.parent.parent, curr.parent.parent.parent, Path.cwd()]:
        target = parent / "backend" / "app" / "schemas" / "maintenance.py"
        if target.exists():
            spec = importlib.util.spec_from_file_location("_canonical_maintenance_schemas", target)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_canonical_maintenance_schemas"] = mod
                spec.loader.exec_module(mod)
                return mod

    raise ImportError("Could not locate canonical maintenance schemas (backend/app/schemas/maintenance.py)")


_m = _resolve_maintenance_module()

AcceptedEvent = _m.AcceptedEvent
ChecklistItem = _m.ChecklistItem
Equipment = _m.Equipment
ForecastResult = _m.ForecastResult
ForecastSnapshot = _m.ForecastSnapshot
ImageLabelScore = _m.ImageLabelScore
ItemPhotoReview = _m.ItemPhotoReview
OperationVersion = _m.OperationVersion
PhotoReport = _m.PhotoReport
PhotoReviewRequest = _m.PhotoReviewRequest
PhotoReviewResult = _m.PhotoReviewResult
RecurrenceRule = _m.RecurrenceRule
RuntimeReading = _m.RuntimeReading
Site = _m.Site
Uncertainty = _m.Uncertainty

__all__ = [
    "AcceptedEvent",
    "ChecklistItem",
    "Equipment",
    "ForecastResult",
    "ForecastSnapshot",
    "ImageLabelScore",
    "ItemPhotoReview",
    "OperationVersion",
    "PhotoReport",
    "PhotoReviewRequest",
    "PhotoReviewResult",
    "RecurrenceRule",
    "RuntimeReading",
    "Site",
    "Uncertainty",
]
