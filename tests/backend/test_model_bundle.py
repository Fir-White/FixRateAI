"""Portable RF bundle image and Compose contract checks, without legacy CLIP packaging."""
from pathlib import Path
import ast
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_build_bundled_image_drops_clip_and_pins_rf_only():
    source = (ROOT / "scripts/build_bundled_image.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert "model_pin" not in defined_names
    assert "export_pinned_cache" not in defined_names
    assert "clip_model_name" not in source and "clip_revision" not in source
    assert "load_verified_forecaster" in source

    dockerfile = (ROOT / "Dockerfile.bundled").read_text(encoding="utf-8")
    assert 'LABEL org.fixrate.models="rf-bundled"' in dockerfile
    assert "CLIP" not in dockerfile and "model-cache" not in dockerfile


def test_bundled_runtime_keeps_database_and_photo_storage_contract():
    regular = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    bundled = yaml.safe_load((ROOT / "compose.bundled.yaml").read_text(encoding="utf-8"))
    assert bundled["services"]["db"] == regular["services"]["db"]
    assert bundled["volumes"] == regular["volumes"]
    app = bundled["services"]["app"]
    assert "build" not in app
    assert app["volumes"] == regular["services"]["app"]["volumes"]
    assert app["environment"]["DATABASE_URL"] == regular["services"]["app"]["environment"]["DATABASE_URL"]
    for legacy_key in ("HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        assert legacy_key not in app["environment"]
    deploy = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text(encoding="utf-8"))
    deploy_env = deploy["x-application"]["environment"]
    assert deploy_env["PHOTO_REVIEW_PROVIDER"] == "${PHOTO_REVIEW_PROVIDER:-aitunnel}"
    assert deploy_env["FIXRATE_LLM_LOCAL_ONLY"] == "1"
    assert "AITUNNEL_API_KEY" not in deploy_env and "AI_TUNNEL_API_KEY" not in deploy_env
    class ComposeLoader(yaml.SafeLoader):
        pass
    ComposeLoader.add_constructor("!override", lambda parser, node: parser.construct_sequence(node))
    services = yaml.load((ROOT / "deploy/compose.cloud.yaml").read_text(encoding="utf-8"), Loader=ComposeLoader)["services"]
    cloud = services["api"]["environment"]
    assert cloud["AITUNNEL_API_KEY"] == "${AITUNNEL_API_KEY:?Set a private AI Tunnel key}"
    assert cloud["AITUNNEL_VISION_MODEL"] == "${AITUNNEL_VISION_MODEL:-qwen3.7-flash}"
    assert services["web"]["ports"] == ["127.0.0.1:${FIXRATE_PORT:-8080}:8080"]
    assert "HF_HUB_OFFLINE" not in deploy_env and "TRANSFORMERS_OFFLINE" not in deploy_env
