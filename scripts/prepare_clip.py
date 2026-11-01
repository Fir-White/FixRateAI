"""Explicitly prepare pinned CLIP weights; API requests themselves stay offline.

Run only in an environment with ml_service/requirements-cv.txt installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Explicit network download of pinned public weights")
    args = parser.parse_args()
    from ml_service.app.core.config import settings
    if args.download:
        from huggingface_hub import snapshot_download
        snapshot_download(settings.clip_model_name, revision=settings.clip_revision, token=False,
                          allow_patterns=["config.json", "preprocessor_config.json", "tokenizer_config.json",
                                          "tokenizer.json", "special_tokens_map.json", "vocab.json", "merges.txt",
                                          "pytorch_model.bin"])
    from ml_service.app.cv.classifier import CLIPZeroShotClassifier
    classifier = CLIPZeroShotClassifier()
    if not classifier.is_torch_active:
        raise RuntimeError("CLIP is not ready: install the optional stack and prepare the pinned local cache")
    print(json.dumps({"status": "ready", "model_ref": classifier.model_ref,
                      "note": "Readiness only; real HTTP inference is checked with FIXRATE_REQUIRE_CLIP=1 scripts/verify.py"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
