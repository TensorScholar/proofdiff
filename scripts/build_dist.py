"""Build and verify ProofDiff's canonical PEP 517 distribution set.

Package metadata and archive construction are owned exclusively by the
``pyproject.toml`` PEP 517 backend. This script only prepares a dedicated
release-output directory, invokes that backend, and validates the resulting
public artifact set.

``SOURCE_DATE_EPOCH`` is passed through to the backend when supplied by CI.
It stabilizes wheel timestamps with the current backend, but this script does
not claim byte-for-byte reproducible sdists.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIST = ROOT / "dist"
VERSION_FILE = ROOT / "src" / "proofdiff" / "_version.py"
DIST_NAME = "proofdiff"
SBOM_NAME = "proofdiff-sbom.cdx.json"
CHECKSUM_NAME = "SHA256SUMS"


@dataclass(frozen=True)
class DistributionSet:
    output_dir: Path
    wheel: Path
    sdist: Path


def package_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").split('"')[1]


def output_directory(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def expected_distribution_names(version: str | None = None) -> set[str]:
    value = version or package_version()
    return {
        f"{DIST_NAME}-{value}-py3-none-any.whl",
        f"{DIST_NAME}-{value}.tar.gz",
    }


def expected_public_asset_names(version: str | None = None) -> set[str]:
    return {*expected_distribution_names(version), SBOM_NAME}


def expected_release_file_names(version: str | None = None) -> set[str]:
    return {*expected_public_asset_names(version), CHECKSUM_NAME}


def managed_artifact_name(name: str) -> bool:
    return name in {SBOM_NAME, CHECKSUM_NAME} or bool(re.fullmatch(rf"{DIST_NAME}-.+\.(?:whl|tar\.gz)", name))


def prepare_output_directory(path: Path) -> Path:
    """Create an empty artifact directory without deleting unrelated files."""
    output = output_directory(path)
    if output == ROOT or output == ROOT.parent:
        raise SystemExit(f"refusing to use unsafe release output directory: {output}")
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise SystemExit(f"release output directory is unsafe: {output}")
        children = list(output.iterdir())
        unsafe = [child for child in children if child.is_symlink() or not child.is_file()]
        unexpected = [child for child in children if not managed_artifact_name(child.name)]
        if unsafe or unexpected:
            names = ", ".join(child.name for child in [*unsafe, *unexpected])
            raise SystemExit(f"refusing to remove unexpected release-output paths: {names}")
        for child in children:
            child.unlink()
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def regular_files(path: Path) -> dict[str, Path]:
    output = output_directory(path)
    if output.is_symlink() or not output.is_dir():
        raise SystemExit(f"release output directory is missing or unsafe: {output}")
    files: dict[str, Path] = {}
    for child in output.iterdir():
        if child.is_symlink() or not child.is_file():
            raise SystemExit(f"unexpected non-file in release output: {child.name}")
        files[child.name] = child
    return files


def require_exact_files(path: Path, expected: set[str]) -> dict[str, Path]:
    files = regular_files(path)
    actual = set(files)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected: {', '.join(unexpected)}")
        raise SystemExit("release artifact set is invalid (" + "; ".join(detail) + ")")
    return files


def validate_distribution_set(path: Path) -> DistributionSet:
    output = output_directory(path)
    files = require_exact_files(output, expected_distribution_names())
    version = package_version()
    return DistributionSet(
        output_dir=output,
        wheel=files[f"{DIST_NAME}-{version}-py3-none-any.whl"],
        sdist=files[f"{DIST_NAME}-{version}.tar.gz"],
    )


def build_distributions(path: Path = DIST) -> DistributionSet:
    output = prepare_output_directory(path)
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output)],
        cwd=ROOT,
        check=True,
    )
    return validate_distribution_set(output)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_checksum_manifest(path: Path) -> None:
    output = output_directory(path)
    files = require_exact_files(output, expected_release_file_names())
    checksum = files[CHECKSUM_NAME]
    lines = checksum.read_text(encoding="utf-8").splitlines()
    expected_names = expected_public_asset_names()
    if len(lines) != len(expected_names):
        raise SystemExit("checksum manifest has an unexpected number of entries")

    recorded: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or not name:
            raise SystemExit(f"invalid checksum manifest entry: {line!r}")
        if name in recorded:
            raise SystemExit(f"duplicate checksum manifest entry: {name}")
        recorded[name] = digest
    if set(recorded) != expected_names:
        raise SystemExit("checksum manifest does not cover the expected public artifact set")
    for name, digest in recorded.items():
        if sha256(files[name]) != digest:
            raise SystemExit(f"checksum mismatch: {name}")


def write_checksum_manifest(path: Path = DIST) -> Path:
    """Checksum public assets; SHA256SUMS deliberately does not checksum itself."""
    output = output_directory(path)
    files = require_exact_files(output, expected_public_asset_names())
    checksum = output / CHECKSUM_NAME
    assets = sorted(expected_public_asset_names())
    checksum.write_text(
        "".join(f"{sha256(files[name])}  {name}\n" for name in assets),
        encoding="utf-8",
    )
    verify_checksum_manifest(output)
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ProofDiff's canonical PEP 517 release artifacts")
    parser.add_argument("--outdir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--write-checksums",
        action="store_true",
        help="write and verify SHA256SUMS for an existing wheel, sdist, and SBOM",
    )
    args = parser.parse_args()
    if args.write_checksums:
        print(write_checksum_manifest(args.outdir))
    else:
        artifacts = build_distributions(args.outdir)
        print(artifacts.wheel)
        print(artifacts.sdist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
