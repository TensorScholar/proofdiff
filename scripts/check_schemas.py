from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]


def load(path: Path):  # type: ignore[no-untyped-def]
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_name: str, paths: list[Path], *, jsonl: bool = False) -> None:
    validator = Draft202012Validator(load(ROOT / "schemas" / schema_name))
    for path in paths:
        if jsonl:
            values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            values = [load(path)]
        for index, value in enumerate(values):
            errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
            if errors:
                location = f"{path}:{index + 1}" if jsonl else str(path)
                details = "; ".join(error.message for error in errors)
                raise SystemExit(f"schema validation failed for {location}: {details}")


def main() -> int:
    example = ROOT / "examples" / "support-agent"
    validate(
        "manifest.schema.json",
        [
            example / "baseline-manifest.json",
            example / "candidate-block-manifest.json",
            example / "candidate-review-manifest.json",
        ],
    )
    validate("contract.schema.json", sorted((example / "contracts").glob("*.json")))
    validate("trace.schema.json", sorted((example / "traces").glob("*.jsonl")), jsonl=True)
    validate("policy.schema.json", [example / "policy.json"])
    print("Schema validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
