from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask

from atlanticus.web.environment import resolve_environment
from atlanticus.web.identity.errors import IdentityConfigurationError

_LOCAL_SECRET_PATH = Path('.runtime') / 'identity' / 'session.key'


def configure_identity_session(server: Flask) -> None:
    environment = resolve_environment()
    if not server.secret_key:
        if environment.is_production:
            raise IdentityConfigurationError(
                'Flask SECRET_KEY is required for identity in production'
            )
        server.secret_key = _load_or_create_secret(Path.cwd() / _LOCAL_SECRET_PATH)

    server.config['SESSION_COOKIE_HTTPONLY'] = True
    if not server.config.get('SESSION_COOKIE_SAMESITE'):
        server.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    if environment.is_production:
        server.config['SESSION_COOKIE_SECURE'] = True


def _load_or_create_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return _read_secret(path)

    temporary = path.with_name(f'.{path.name}.{secrets.token_hex(8)}.tmp')
    secret = secrets.token_urlsafe(48)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
    return _read_secret(path)


def _read_secret(path: Path) -> str:
    value = path.read_text(encoding='utf-8').strip()
    if not value:
        raise IdentityConfigurationError('Local identity session key is empty')
    return value
