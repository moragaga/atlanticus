from __future__ import annotations

import hashlib

from atlanticus.web.users.errors import UsersDefinitionError


def _required_identity_part(value: str | None, *, label: str) -> str:
    if value is None:
        raise UsersDefinitionError(f'{label} must not be empty')
    normalized = value.strip()
    if not normalized:
        raise UsersDefinitionError(f'{label} must not be empty')
    return normalized


def build_user_key(*, issuer: str | None, subject_id: str | None) -> str:
    normalized_issuer = _required_identity_part(issuer, label='User issuer')
    normalized_subject_id = _required_identity_part(subject_id, label='User subject id')
    material = f'{normalized_issuer}|{normalized_subject_id}'.encode('utf-8')
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f'user:{digest}'
