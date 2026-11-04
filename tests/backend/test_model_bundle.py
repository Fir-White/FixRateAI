"""Pinned model-cache packaging checks; fixtures are files, not ML inference."""
import json
from pathlib import Path

import pytest

from scripts.build_bundled_image import MODEL_FILES, export_pinned_cache, model_pin


def cache_fixture(tmp_path):
    cache = tmp_path / "cache"
    model, revision = model_pin()
    snapshot = cache / "hub" / ("models--" + model.replace("/", "--")) / "snapshots" / revision
    snapshot.mkdir(parents=True)
    for name in MODEL_FILES:
        (snapshot / name).write_bytes(("fixture-only:" + name).encode())
    (cache / "token").write_text("private-hf-credential", encoding="utf-8")
    (snapshot / "extra-secret.txt").write_text("private-extra", encoding="utf-8")
    return cache, model, revision


def test_export_contains_only_pinned_model_files_and_no_credentials(tmp_path):
    cache, model, revision = cache_fixture(tmp_path)
    output = tmp_path / "export"
    manifest = export_pinned_cache(cache, output, model, revision)
    assert manifest["model_ref"] == model + "@" + revision
    assert set(manifest["files"]) == set(MODEL_FILES)
    contents = b"".join(p.read_bytes() for p in output.rglob("*") if p.is_file())
    assert b"private-hf-credential" not in contents and b"private-extra" not in contents
    metadata = json.loads((output / "bundle-manifest.json").read_text(encoding="utf-8"))
    assert all(len(item["sha256"]) == 64 for item in metadata["files"].values())


def test_missing_pinned_revision_does_not_export_partial_context(tmp_path):
    cache, model, revision = cache_fixture(tmp_path)
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="snapshot"):
        export_pinned_cache(cache, output, model, "0" * 40)
    assert not output.exists()


def test_export_does_not_overwrite_previous_bundle(tmp_path):
    cache, model, revision = cache_fixture(tmp_path)
    output = tmp_path / "export"
    output.mkdir()
    (output / "keep").write_text("previous", encoding="utf-8")
    with pytest.raises(ValueError, match="new directory"):
        export_pinned_cache(cache, output, model, revision)
    assert (output / "keep").read_text(encoding="utf-8") == "previous"


def test_missing_file_does_not_create_output(tmp_path):
    cache, model, revision = cache_fixture(tmp_path)
    snapshot = cache / "hub" / ("models--" + model.replace("/", "--")) / "snapshots" / revision
    (snapshot / "tokenizer.json").unlink()
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="model file"):
        export_pinned_cache(cache, output, model, revision)
    assert not output.exists()


def test_bundled_runtime_keeps_database_and_photo_storage_contract():
    import yaml
    root = Path(__file__).resolve().parents[2]
    regular = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    bundled = yaml.safe_load((root / "compose.bundled.yaml").read_text(encoding="utf-8"))
    assert bundled["services"]["db"] == regular["services"]["db"]
    assert bundled["volumes"] == regular["volumes"]
    app = bundled["services"]["app"]
    assert "build" not in app
    assert app["volumes"] == regular["services"]["app"]["volumes"]
    assert app["environment"]["DATABASE_URL"] == regular["services"]["app"]["environment"]["DATABASE_URL"]
    assert app["environment"]["HF_HOME"] == "/app/model-cache"
    assert app["environment"]["HF_HUB_OFFLINE"] == "1"
