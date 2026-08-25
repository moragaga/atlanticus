from __future__ import annotations

# Reduce el riesgo de filtrar secretos o payloads excesivos en logs web.

from collections.abc import Mapping
from typing import Any

_REDACTED = '[REDACTED]'
_SECRET_KEYS = {
    'access_token',
    'authorization',
    'client_secret',
    'cookie',
    'password',
    'refresh_token',
    'sas',
    'secret',
    'session',
}


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return '[TRUNCATED]'
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _is_secret_key(str(key)) else sanitize(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return value if len(value) <= 512 else f'{value[:509]}...'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().lower().replace('-', '_')
    return (
        normalized in _SECRET_KEYS
        or normalized.endswith('_secret')
        or normalized.endswith('_token')
    )
