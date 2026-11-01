from pathlib import Path

import pytest

from scripts.verification_paths import log_reference, prepare_run


def test_default_run_pairs_reports_and_logs_outside_callers_directory(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    reports, logs = prepare_run(root=workspace)
    assert reports.parent == workspace / "reports/verification"
    assert logs.parent == workspace / "logs/verification"
    assert reports.name == logs.name
    (logs / "pytest.log").write_text("passed", encoding="utf-8")
    assert (reports / log_reference(reports, logs / "pytest.log")).read_text(encoding="utf-8") == "passed"
    assert not (elsewhere / "reports").exists()


def test_report_destination_cannot_repopulate_documentation(tmp_path):
    with pytest.raises(ValueError, match="under reports/"):
        prepare_run(tmp_path / "docs/verification/run", root=tmp_path)
    assert not (tmp_path / "docs").exists()


def test_rerun_preserves_previous_evidence(tmp_path):
    output = tmp_path / "reports/verification/fixed-run"
    reports, logs = prepare_run(output, root=tmp_path)
    (reports / "results.json").write_text("[]", encoding="utf-8")
    (logs / "pytest.log").write_text("original", encoding="utf-8")
    with pytest.raises(ValueError, match="already has results"):
        prepare_run(output, root=tmp_path)
    assert (logs / "pytest.log").read_text(encoding="utf-8") == "original"


def test_external_ci_output_retains_a_resolvable_log_reference(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    reports, logs = prepare_run(tmp_path / "ci-artifacts", root=workspace)
    assert reports == tmp_path / "ci-artifacts"
    assert logs == workspace / "logs/verification/ci-artifacts"
    assert (reports / log_reference(reports, logs / "api.log")).resolve() == logs / "api.log"
    with monkeypatch.context() as patch:
        def different_volumes(*args):
            raise ValueError("path is on a different drive")
        patch.setattr("scripts.verification_paths.os.path.relpath", different_volumes)
        reference = log_reference(reports, logs / "api.log")
    assert Path(reference).is_absolute()
    assert (reports / reference).resolve() == logs / "api.log"
