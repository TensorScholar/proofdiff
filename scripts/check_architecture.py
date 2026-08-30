from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "proofdiff"

FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "domain": ("proofdiff.engine", "proofdiff.cli", "proofdiff.reporting"),
    "engine": ("proofdiff.cli", "proofdiff.reporting"),
    "reporting": ("proofdiff.cli",),
}
NETWORK_MODULES = ("httpx", "requests", "urllib.request", "socket", "aiohttp")

ALLOWED_ROOT_ENTRIES = frozenset(
    {
        ".github",
        ".gitignore",
        "CHANGELOG.md",
        "CITATION.cff",
        "CONTRIBUTING.md",
        "LICENSE",
        "MANIFEST.in",
        "Makefile",
        "README.md",
        "SECURITY.md",
        "benchmarks",
        "docs",
        "examples",
        "pyproject.toml",
        "schemas",
        "scripts",
        "src",
        "tests",
    }
)
REQUIRED_ROOT_ENTRIES = frozenset(
    {
        ".github",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        "docs",
        "pyproject.toml",
        "src",
        "tests",
    }
)
ALLOWED_DOC_ENTRIES = frozenset(
    {
        "architecture.md",
        "assets",
        "benchmark-card.md",
        "evidence-model.md",
        "limitations.md",
        "threat-model.md",
    }
)
FORBIDDEN_PUBLIC_BASENAMES = frozenset(
    {
        "AGENTS.md",
        "AUTONOMY_POLICY.md",
        "GITHUB_MIGRATION.md",
        "GLOBAL_CONSTRAINTS.md",
        "PROJECT_STATUS.md",
        "PROTECTED_FILE_MANIFEST.json",
        "PUBLISHING.md",
        "README_START_HERE.md",
        "REPORT_TEMPLATE.md",
        "SELF_AUDIT_CHECKLIST.md",
        "START_PROMPT_FOR_CODEX.md",
        "STOP_CONDITIONS.md",
        "TASK_GRAPH.yaml",
        "VALIDATION_POLICY.md",
        "commercial-support.md",
        "migration-from-axiom.md",
        "release-readiness.md",
        "security-audit.md",
    }
)
FORBIDDEN_PUBLIC_NAME_TOKENS = ("autopilot", "codex", "handoff", "self_audit", "task_graph")


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def tracked_paths() -> list[PurePosixPath]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [PurePosixPath(os.fsdecode(raw)) for raw in completed.stdout.split(b"\0") if raw]


def check_public_repository_surface(findings: list[str]) -> None:
    paths = tracked_paths()
    top_level = {path.parts[0] for path in paths if path.parts}
    docs_entries = {path.parts[1] for path in paths if len(path.parts) >= 2 and path.parts[0] == "docs"}

    for entry in sorted(top_level - ALLOWED_ROOT_ENTRIES):
        findings.append(f"repository root contains unapproved public entry: {entry}")
    for entry in sorted(REQUIRED_ROOT_ENTRIES - top_level):
        findings.append(f"repository root is missing required public entry: {entry}")
    for entry in sorted(docs_entries - ALLOWED_DOC_ENTRIES):
        findings.append(f"docs contains unapproved public entry: {entry}")

    for path in paths:
        basename = path.name
        basename_lower = basename.lower()
        if ".axiom" in path.parts:
            findings.append(f"internal AXIOM control-plane artifact must not be tracked: {path}")
        if basename in FORBIDDEN_PUBLIC_BASENAMES:
            findings.append(f"internal orchestration/migration artifact must not be public: {path}")
        if any(token in basename_lower for token in FORBIDDEN_PUBLIC_NAME_TOKENS):
            findings.append(f"internal tool/handoff artifact must not be public: {path}")


def main() -> int:
    findings: list[str] = []
    check_public_repository_surface(findings)

    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        layer = relative.parts[0] if len(relative.parts) > 1 else "root"
        imports = imported_modules(path)
        for prefix in FORBIDDEN_IMPORTS.get(layer, ()):
            for module in imports:
                if relative.as_posix() == "engine/pipeline.py" and module == "proofdiff.reporting":
                    continue
                if module == prefix or module.startswith(prefix + "."):
                    findings.append(f"{relative}: {layer} must not import {module}")
        if layer in {"domain", "engine"}:
            for module in imports:
                if module in NETWORK_MODULES or module.startswith(tuple(item + "." for item in NETWORK_MODULES)):
                    findings.append(f"{relative}: deterministic core must not import network module {module}")

    if findings:
        raise SystemExit("Architecture check failed:\n" + "\n".join(findings))
    print("Architecture check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
