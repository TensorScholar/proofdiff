from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
VERSION = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]
WHEEL = ROOT / "dist" / f"proofdiff-{VERSION}-py3-none-any.whl"


def run(command: list[str], *, cwd: Path | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode != expected:
        raise SystemExit(
            f"command failed ({completed.returncode}, expected {expected}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def canonical_wheel() -> Path:
    if not WHEEL.is_file():
        run([sys.executable, str(ROOT / "scripts" / "build_dist.py")])
    if not WHEEL.is_file():
        raise SystemExit(f"canonical wheel is missing: {WHEEL}")
    return WHEEL


def smoke_base_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="proofdiff-smoke-") as raw:
        temp = Path(raw).resolve(strict=True)
        venv = temp / "venv"
        run([sys.executable, "-m", "venv", str(venv)])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        proofdiff = venv / ("Scripts/proofdiff.exe" if os.name == "nt" else "bin/proofdiff")
        run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
        version = run([str(proofdiff), "--version"])
        if version.stdout.strip() != f"proofdiff {VERSION}":
            raise SystemExit(f"unexpected version output: {version.stdout!r}")
        run([str(python), "-c", "import proofdiff"])
        example = ROOT / "examples" / "support-agent"
        evidence = temp / "evidence"
        run(
            [
                str(proofdiff),
                "check",
                "--baseline",
                str(example / "baseline-manifest.json"),
                "--candidate",
                str(example / "candidate-block-manifest.json"),
                "--contracts",
                str(example / "contracts"),
                "--baseline-traces",
                str(example / "traces" / "baseline.jsonl"),
                "--candidate-traces",
                str(example / "traces" / "candidate-block.jsonl"),
                "--evidence",
                str(evidence),
            ],
            expected=2,
        )
        run([str(proofdiff), "verify", "--evidence", str(evidence)])


def smoke_yaml_extra_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="proofdiff-yaml-smoke-") as raw:
        temp = Path(raw).resolve(strict=True)
        venv = temp / "venv"
        run([sys.executable, "-m", "venv", str(venv)])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        requirement = f"proofdiff[yaml] @ {wheel.resolve().as_uri()}"
        run([str(python), "-m", "pip", "install", requirement])
        run([str(python), "-c", "import proofdiff; import yaml"])


def smoke_install(wheel: Path) -> None:
    smoke_base_install(wheel)
    smoke_yaml_extra_install(wheel)


def main() -> int:
    smoke_install(canonical_wheel())
    print("Clean-wheel smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
