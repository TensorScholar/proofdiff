from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "proofdiff"

FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "domain": ("proofdiff.engine", "proofdiff.cli", "proofdiff.reporting"),
    "engine": ("proofdiff.cli", "proofdiff.reporting"),
    "reporting": ("proofdiff.cli",),
}
NETWORK_MODULES = ("httpx", "requests", "urllib.request", "socket", "aiohttp")


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def main() -> int:
    findings: list[str] = []
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
