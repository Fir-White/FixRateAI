"""Inspect any before/after photo pair with FixRateAI Quality Guard and CLIP.

Usage:
    .venv/bin/python scripts/inspect_my_photos.py <before_photo> <after_photo> [--confirmed]
"""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

# Ensure project root is in python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_service.app.cv.service import review_photos
from ml_service.app.schemas import PhotoReviewRequest


def main():
    parser = argparse.ArgumentParser(description="Inspect before/after photo pair with CLIP and QualityGuard")
    parser.add_argument("before", type=Path, help="Path to photo before maintenance")
    parser.add_argument("after", type=Path, help="Path to photo after maintenance")
    parser.add_argument("--confirmed", action="store_true", default=True, help="Engineer confirmed comparable view")
    args = parser.parse_args()

    if not args.before.is_file():
        sys.exit(f"Error: file not found: {args.before}")
    if not args.after.is_file():
        sys.exit(f"Error: file not found: {args.after}")

    # Load canonical example request payload
    examples_path = ROOT / "contracts/examples/maintenance.json"
    with open(examples_path, "r", encoding="utf-8") as f:
        examples = json.load(f)["examples"]
    ex = next(x for x in examples if x["name"] == "photo_review_request")
    req = PhotoReviewRequest.model_validate_json(json.dumps(ex["payload"]))

    storage = {
        req.photos[0].photo_id: args.before.read_bytes(),
        req.photos[1].photo_id: args.after.read_bytes(),
    }

    result = review_photos(
        req,
        photo_loader=lambda pid: storage[pid],
        comparability_confirmed=lambda b, a: args.confirmed,
    )

    print(json.dumps(json.loads(result.model_dump_json()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
