from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from proofdiff.domain.errors import InputError

MAX_DEPTH = 64
MAX_COLLECTION_ITEMS = 100_000
SECRET_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)
SAFE_SECRET_REFERENCE_PREFIXES = (
    "${",
    "env:",
    "secret://",
    "vault://",
    "aws-sm://",
    "gcp-sm://",
    "azure-kv://",
    "opaque://",
)


def normalize(value: Any, *, _depth: int = 0) -> Any:
    if _depth > MAX_DEPTH:
        raise InputError(f"document nesting exceeds {MAX_DEPTH}")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InputError("non-finite numbers are not permitted")
        return value
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise InputError("collection exceeds item limit")
        return [normalize(item, _depth=_depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise InputError("mapping exceeds item limit")
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise InputError("mapping keys must be strings")
            normalized[key] = normalize(value[key], _depth=_depth + 1)
        return normalized
    raise InputError(f"unsupported value type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    normalized = normalize(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(fragment in normalized for fragment in SECRET_FRAGMENTS)


def is_safe_secret_reference(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped == "<redacted>" or stripped.startswith(SAFE_SECRET_REFERENCE_PREFIXES)


def redact_secrets(value: Any) -> Any:
    """Redact secret-like leaf values without changing non-secret structure."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if is_secret_key(key) and not is_safe_secret_reference(item):
                result[key] = "<redacted>"
            else:
                result[key] = redact_secrets(item)
        return result
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
