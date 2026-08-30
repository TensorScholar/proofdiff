from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
VERSION = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a minimal CycloneDX SBOM for ProofDiff.")
    parser.add_argument("--out", default="dist/proofdiff-sbom.cdx.json")
    args = parser.parse_args()
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:proofdiff-{VERSION}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:pypi/proofdiff@{VERSION}",
                "name": "proofdiff",
                "version": VERSION,
                "licenses": [{"license": {"id": "Apache-2.0"}}],
                "purl": f"pkg:pypi/proofdiff@{VERSION}",
            }
        },
        "components": [],
        "dependencies": [{"ref": f"pkg:pypi/proofdiff@{VERSION}", "dependsOn": []}],
        "properties": [
            {"name": "proofdiff:runtime-dependencies", "value": "none"},
            {"name": "proofdiff:scope", "value": "project-declared runtime dependency graph"},
        ],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
