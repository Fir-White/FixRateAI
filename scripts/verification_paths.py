"""Shared output locations for verification tools, independent of the caller's cwd."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import os

ROOT = Path(__file__).resolve().parents[1]


def prepare_run(output=None, *, prefix="verify", root=ROOT):
    root = Path(root).resolve()
    run_id = f"{prefix}-{datetime.now().astimezone():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    reports = Path(output).resolve() if output is not None else root / "reports/verification" / run_id
    if reports.is_relative_to(root) and not reports.is_relative_to(root / "reports"):
        raise ValueError("Verification output inside the repository must be under reports/")
    if (reports / "results.json").exists() or (reports / "orchestration_cases.json").exists():
        raise ValueError("This run already has results; choose a new output directory")
    relative = reports.relative_to(root / "reports") if reports.is_relative_to(root / "reports") else Path("verification") / reports.name
    logs = root / "logs" / relative
    if logs.exists() and any(logs.iterdir()):
        raise ValueError("This run already has logs; choose a new output directory")
    reports.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return reports, logs


def log_reference(reports, file):
    try:
        return Path(os.path.relpath(file, reports)).as_posix()
    except ValueError:
        # Windows volumes cannot share a relative path (e.g. external CI output).
        return Path(file).resolve().as_posix()
