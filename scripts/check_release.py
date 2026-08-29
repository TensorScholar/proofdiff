from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    env = os.environ.copy()
    source_path = str(ROOT / "src")
    env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def check_version_consistency() -> None:
    version = (ROOT / "src" / "proofdiff" / "_version.py").read_text(encoding="utf-8").split('"')[1]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    if version not in changelog or f"version: {version}" not in citation:
        raise SystemExit("version metadata is inconsistent")


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


def main() -> int:
    check_version_consistency()
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
    run([sys.executable, "benchmarks/run_benchmark.py"])
    run([sys.executable, "scripts/build_dist.py"])
    run([sys.executable, "scripts/generate_sbom.py"])
    run([sys.executable, "scripts/smoke_install.py"])
    print("Release checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
