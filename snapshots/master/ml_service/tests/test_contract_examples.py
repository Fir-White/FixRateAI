"""Machine validation of the versioned integration contract examples."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[2]
CONTRACTS = ROOT / "docs" / "contracts" / "fixrate-contracts.json"
EXAMPLES = ROOT / "docs" / "contracts" / "examples.json"


def test_contract_examples_match_schema():
    document = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    validators = {
        name: Draft202012Validator({"$ref": f"#/$defs/{name}", **document})
        for name in ("JobRequest", "JobResponse", "ErrorResponse")
    }

    validators["JobRequest"].validate(examples["successful_request"])
    validators["JobResponse"].validate(examples["incomplete_response"])
    validators["JobResponse"].validate(examples["successful_response"])
    validators["ErrorResponse"].validate(examples["invalid_unit_error"])
    validators["ErrorResponse"].validate(examples["missing_scale_error"])


def test_invalid_unit_is_rejected():
    document = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLES.read_text(encoding="utf-8"))["successful_request"]
    example["measurements"][0]["unit"] = "meters"
    validator = Draft202012Validator({"$ref": "#/$defs/JobRequest", **document})
    with pytest.raises(Exception):
        validator.validate(example)
