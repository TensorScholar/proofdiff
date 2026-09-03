from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an all-contracts ProofDiff baseline.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    files = sorted(args.source.glob("*.json"))
    if not files:
        raise SystemExit("no contracts found")
    for source in files:
        contract = _load(source)
        contract["always_run"] = True
        destination = args.output / source.name
        destination.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"generated {len(files)} all-run contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
