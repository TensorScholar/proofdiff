from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCAN_ROOTS = [ROOT / "src", ROOT / "scripts", ROOT / ".github"]
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".json", ".toml", ".md"}
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _scan_python(path: Path, text: str) -> list[str]:
    findings: list[str] = []
    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in {"eval", "exec"}:
            findings.append(f"{path.relative_to(ROOT)}:{node.lineno}: dynamic {name}")
        if name in {"pickle.load", "pickle.loads"}:
            findings.append(f"{path.relative_to(ROOT)}:{node.lineno}: unsafe pickle deserialization")
        if name in {"yaml.full_load", "yaml.unsafe_load"}:
            findings.append(f"{path.relative_to(ROOT)}:{node.lineno}: unsafe YAML loader")
        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                findings.append(f"{path.relative_to(ROOT)}:{node.lineno}: subprocess shell=True")
    return findings


def main() -> int:
    findings: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            if PRIVATE_KEY.search(text):
                findings.append(f"{path.relative_to(ROOT)}: private key material")
            if path.suffix == ".py":
                findings.extend(_scan_python(path, text))
    if findings:
        raise SystemExit("Security scan failed:\n" + "\n".join(findings))
    print("Security scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
