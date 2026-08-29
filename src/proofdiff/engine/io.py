from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from proofdiff.domain.errors import InputError
from proofdiff.engine.canonical import normalize

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_JSONL_RECORDS = 100_000


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        try:
            if component.is_symlink():
                raise InputError(f"symbolic-link path components are not accepted: {component}")
        except OSError as exc:
            raise InputError(f"cannot inspect input path component: {component}") from exc


def _read_text(path: Path) -> str:
    _reject_symlink_components(path)
    try:
        if path.is_symlink():
            raise InputError(f"symbolic-link inputs are not accepted: {path}")
        size = path.stat().st_size
    except InputError:
        raise
    except OSError as exc:
        raise InputError(f"cannot stat input: {path}") from exc
    if not path.is_file():
        raise InputError(f"input is not a regular file: {path}")
    if size > MAX_FILE_BYTES:
        raise InputError(f"input exceeds {MAX_FILE_BYTES} bytes: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputError(f"cannot read UTF-8 input: {path}") from exc


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def _unique_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonfinite_constant,
    )


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise InputError("YAML input requires the optional dependency: pip install 'proofdiff[yaml]'") from exc

    class UniqueKeySafeLoader(yaml.SafeLoader):  # type: ignore[misc, name-defined]
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[str, Any]:
        loader.flatten_mapping(node)
        pairs = loader.construct_pairs(node, deep=deep)
        return _unique_object(pairs)

    UniqueKeySafeLoader.add_constructor(  # type: ignore[attr-defined]
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )
    return yaml.load(text, Loader=UniqueKeySafeLoader)


def load_document(path: str | Path) -> Any:
    source = Path(path)
    text = _read_text(source)
    suffix = source.suffix.lower()
    try:
        value = _load_yaml(text) if suffix in {".yaml", ".yml"} else _load_json(text)
        return normalize(value)
    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"invalid document {source}: {exc}") from exc


def load_object(path: str | Path) -> dict[str, Any]:
    value = load_document(path)
    if not isinstance(value, dict):
        raise InputError(f"expected an object at document root: {path}")
    return value


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = _read_text(source)
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if len(records) >= MAX_JSONL_RECORDS:
            raise InputError(f"JSONL exceeds {MAX_JSONL_RECORDS} records: {source}")
        try:
            value = normalize(_load_json(line))
        except Exception as exc:
            raise InputError(f"invalid JSONL at {source}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise InputError(f"expected JSON object at {source}:{line_number}")
        records.append(value)
    return records


def _atomic_write_text(target: Path, payload: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    normalized = normalize(value)
    payload = json.dumps(
        normalized,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    _atomic_write_text(target, payload)


def write_jsonl(path: str | Path, values: list[dict[str, Any]]) -> None:
    target = Path(path)
    lines = [
        json.dumps(
            normalize(value),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        for value in values
    ]
    _atomic_write_text(target, "\n".join(lines) + ("\n" if lines else ""))
