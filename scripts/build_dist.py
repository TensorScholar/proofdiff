from __future__ import annotations

import base64
import gzip
import hashlib
import io
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
DIST = ROOT / "dist"
VERSION_FILE = SRC / "proofdiff" / "_version.py"
VERSION = VERSION_FILE.read_text(encoding="utf-8").split('"')[1]
DIST_NAME = "proofdiff"
WHEEL_NAME = f"{DIST_NAME}-{VERSION}-py3-none-any.whl"
SDIST_NAME = f"{DIST_NAME}-{VERSION}.tar.gz"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def wheel_metadata() -> dict[str, bytes]:
    dist_info = f"{DIST_NAME}-{VERSION}.dist-info"
    metadata = f"""Metadata-Version: 2.4
Name: proofdiff
Version: {VERSION}
Summary: Evidence-first behavioral change analysis for evolving AI systems.
Author: Mohammad Atashi
License-Expression: Apache-2.0
Requires-Python: >=3.11
Description-Content-Type: text/markdown
Project-URL: Homepage, https://github.com/TensorScholar/proofdiff
Project-URL: Repository, https://github.com/TensorScholar/proofdiff

ProofDiff analyzes baseline/candidate changes in AI-system manifests, selects impacted behavioral
contracts, evaluates deterministic fixture traces, and emits scoped PASS/REVIEW/BLOCK evidence.
""".encode()
    wheel = b"Wheel-Version: 1.0\nGenerator: proofdiff-build-dist\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    entry_points = b"[console_scripts]\nproofdiff = proofdiff.cli.main:main\n"
    return {
        f"{dist_info}/METADATA": metadata,
        f"{dist_info}/WHEEL": wheel,
        f"{dist_info}/entry_points.txt": entry_points,
        f"{dist_info}/licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
    }


def record_line(path: str, data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{path},sha256={encoded},{len(data)}"


def tracked_source_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    files: list[Path] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe tracked release path: {relative}")
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"tracked release path is missing or unsafe: {relative.as_posix()}")
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def build_wheel() -> Path:
    DIST.mkdir(exist_ok=True)
    target = DIST / WHEEL_NAME
    files: dict[str, bytes] = {}
    package_root = SRC / "proofdiff"
    for path in tracked_source_files():
        if path.is_relative_to(package_root):
            files[path.relative_to(SRC).as_posix()] = path.read_bytes()
    files.update(wheel_metadata())
    dist_info = f"{DIST_NAME}-{VERSION}.dist-info"
    records = [record_line(path, data) for path, data in sorted(files.items())]
    records.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(records) + "\n").encode()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return target


def include_in_sdist(path: Path) -> bool:
    excluded = {
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "__pycache__",
        ".venv",
        "venv",
        ".proofdiff",
        "htmlcov",
    }
    if any(part in excluded or part.endswith(".egg-info") for part in path.parts):
        return False
    if path.name in {".coverage", ".DS_Store", "coverage.xml", "coverage.json"}:
        return False
    return path.suffix not in {".pyc", ".pyo"}


def build_sdist() -> Path:
    DIST.mkdir(exist_ok=True)
    target = DIST / SDIST_NAME
    prefix = PurePosixPath(f"{DIST_NAME}-{VERSION}")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        metadata = next(data for name, data in wheel_metadata().items() if name.endswith("/METADATA"))
        pkg_info = tarfile.TarInfo(str(prefix / "PKG-INFO"))
        pkg_info.size = len(metadata)
        pkg_info.mtime = 0
        pkg_info.mode = 0o644
        pkg_info.uid = pkg_info.gid = 0
        pkg_info.uname = pkg_info.gname = ""
        archive.addfile(pkg_info, io.BytesIO(metadata))

        for path in tracked_source_files():
            relative = path.relative_to(ROOT)
            if not include_in_sdist(relative):
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(str(prefix / PurePosixPath(relative.as_posix())))
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    with (
        target.open("wb") as handle,
        gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0, compresslevel=9) as zipped,
    ):
        zipped.write(raw.getvalue())
    return target


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    wheel = build_wheel()
    sdist = build_sdist()
    checksum = DIST / "SHA256SUMS"
    checksum.write_text(
        f"{sha256(wheel)}  {wheel.name}\n{sha256(sdist)}  {sdist.name}\n",
        encoding="utf-8",
    )
    print(wheel)
    print(sdist)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
