"""Run real CLIP on explicitly supplied photo pairs; write only hashes and results.

Manifest JSON: [{"before": "path.jpg", "after": "path.jpg", "source": "...",
                 "comparable": true, "visual_verifiability": "visible"}].
These are experimental observations, not evidence of accepted work.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import torch
import transformers
from ml_service.app.cv.classifier import CLIPZeroShotClassifier
from ml_service.app.cv.quality import ImageQualityGuard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="openai/clip-vit-base-patch32")
    parser.add_argument("--revision", default="3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268")
    args = parser.parse_args()
    pairs = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(pairs, list) or len(pairs) < 2:
        raise ValueError("manifest must contain at least two pairs")
    classifier = CLIPZeroShotClassifier(model_name=args.model, revision=args.revision)
    guard = ImageQualityGuard()
    available = classifier.is_torch_active
    records = []
    for pair in pairs:
        before = (args.manifest.parent / pair["before"]).read_bytes()
        after = (args.manifest.parent / pair["after"]).read_bytes()
        b = hashlib.sha256(before).hexdigest()
        a = hashlib.sha256(after).hexdigest()
        record = {"source": pair["source"], "before_sha256": b, "after_sha256": a,
                  "human_comparable": pair.get("comparable"), "visual_verifiability": pair.get("visual_verifiability")}
        if not isinstance(pair.get("comparable"), bool) or pair.get("visual_verifiability") not in ("visible", "not_verifiable"):
            raise ValueError("each pair requires human-assessed comparable and visual_verifiability")
        start = time.perf_counter()
        if b == a:
            record.update(status="uncertain", reason="identical photos")
        elif not available:
            record.update(status="unavailable", reason="MODEL_NOT_READY")
        else:
            review = classifier.evaluate_pair(uuid4(), uuid4(), uuid4(), before, after)
            record.update(raw_clip_verdict=review.verdict, observation=review.observation,
                          scores=[s.score for s in review.scores])
            poor_quality = not guard.assess_bytes(before).is_acceptable or not guard.assess_bytes(after).is_acceptable
            record["status"] = ("not_verifiable" if pair["visual_verifiability"] == "not_verifiable"
                                else "uncertain" if not pair["comparable"] or poor_quality else review.verdict)
            record["quality_acceptable"] = not poor_quality
        record["elapsed_ms"] = round(1000 * (time.perf_counter() - start))
        records.append(record)
    output = {"run_at": datetime.now(timezone.utc).isoformat(), "model_ref": classifier.model_ref if available else None,
              "torch_version": torch.__version__, "transformers_version": transformers.__version__,
              "python": platform.python_version(), "device": "cpu", "pairs": records,
              "limitations": ["Comparability requires human assessment; view and lighting affect the scores.",
                              "The scores are uncalibrated and cannot verify hidden work or acceptance."]}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
