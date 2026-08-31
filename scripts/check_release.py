"""Run release validation for the canonical PEP 517 distribution set."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIST = ROOT / "dist"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    env = os.environ.copy()
    source_path = str(ROOT / "src")
    env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def check_version_consistency(tag: str | None = None) -> None:
    version = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    if version not in changelog or f"version: {version}" not in citation:
        raise SystemExit("version metadata is inconsistent")
    if tag is None:
        print("Tag/version check skipped: no release tag supplied")
        return
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:rc\d+)?", tag):
        raise SystemExit(f"invalid release tag {tag!r}; expected vX.Y.Z or vX.Y.ZrcN")
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise SystemExit(f"tag/version mismatch: {tag} does not match package version {version}")
    print(f"Tag/version check passed: {tag}")


def static_scan() -> None:
    forbidden = {
        r"\beval\s*\(": "eval",
        r"\bexec\s*\(": "exec",
        r"shell\s*=\s*True": "shell=True",
        r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----": "private key",
    }
    findings: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern, label in forbidden.items():
            if re.search(pattern, text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        raise SystemExit("static scan findings:\n" + "\n".join(findings))
    print("Static scan passed")


def canonical_distribution_paths() -> tuple[Path, Path]:
    version = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]
    return (
        DIST / f"proofdiff-{version}-py3-none-any.whl",
        DIST / f"proofdiff-{version}.tar.gz",
    )


def check_wheel_metadata(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        metadata_paths = [path for path in archive.namelist() if path.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise SystemExit("canonical wheel has an invalid METADATA file set")
        metadata = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_paths[0]))
    version = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]
    if metadata["Version"] != version:
        raise SystemExit("canonical wheel version does not match package version")
    extras = metadata.get_all("Provides-Extra", [])
    if "yaml" not in extras:
        raise SystemExit("canonical wheel does not declare the yaml extra")
    requirements = metadata.get_all("Requires-Dist", [])
    normalized = {requirement.replace(" ", "").lower() for requirement in requirements}
    if 'pyyaml>=6.0;extra=="yaml"' not in normalized:
        raise SystemExit("canonical wheel does not require PyYAML for the yaml extra")
    print("Canonical wheel metadata passed: version and yaml extra")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ProofDiff release validation")
    parser.add_argument("--tag", help="Release tag to validate against the package version")
    args = parser.parse_args()
    check_version_consistency(args.tag)
    static_scan()
    run([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts", "benchmarks"])
    if importlib.util.find_spec("ruff"):
        run([sys.executable, "-m", "ruff", "check", "."])
    else:
        print("Ruff unavailable locally; CI remains authoritative")
    if importlib.util.find_spec("mypy"):
        run([sys.executable, "-m", "mypy", "src/proofdiff"])
    else:
        print("mypy unavailable locally; CI remains authoritative")
    run([sys.executable, "-m", "coverage", "erase"])
    run([sys.executable, "-m", "coverage", "run", "--branch", "-m", "pytest", "-q"])
    run([sys.executable, "-m", "coverage", "report", "-m"])
    run([sys.executable, "scripts/check_schemas.py"])
    run([sys.executable, "scripts/check_architecture.py"])
    run([sys.executable, "scripts/security_scan.py"])
    run([sys.executable, "benchmarks/run_benchmark.py", "--no-write"])
    run([sys.executable, "scripts/build_dist.py"])
    wheel, sdist = canonical_distribution_paths()
    if not wheel.is_file() or not sdist.is_file():
        raise SystemExit("canonical release build produced an incomplete distribution set")
    run(
        [
            sys.executable,
            "-m",
            "twine",
            "check",
            str(wheel),
            str(sdist),
        ]
    )
    check_wheel_metadata(wheel)
    run([sys.executable, "scripts/generate_sbom.py"])
    run([sys.executable, "scripts/build_dist.py", "--write-checksums"])
    run([sys.executable, "scripts/smoke_install.py"])
    print("Release checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
