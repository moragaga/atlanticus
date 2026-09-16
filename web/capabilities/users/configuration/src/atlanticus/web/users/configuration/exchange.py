from __future__ import annotations

import gzip
import json
from io import BytesIO
from typing import Any

from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError

_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


def decode_users_profiles_configuration_import(
    payload: bytes,
) -> UsersProfilesConfiguration:
    return UsersProfilesConfiguration.from_document(_decode_document(payload))


def _decode_document(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise UsersConfigurationValidationError('Users configuration file must not be empty')
    if len(payload) > _MAX_COMPRESSED_BYTES:
        raise UsersConfigurationValidationError('Users configuration file exceeds the size limit')
    if payload[:2] != b'\x1f\x8b':
        raise UsersConfigurationValidationError('Users configuration file must be gzip encoded')
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as compressed:
            decoded = compressed.read(_MAX_DECOMPRESSED_BYTES + 1)
    except (OSError, EOFError) as error:
        raise UsersConfigurationValidationError(
            'Users configuration gzip content is invalid'
        ) from error
    if len(decoded) > _MAX_DECOMPRESSED_BYTES:
        raise UsersConfigurationValidationError(
            'Users configuration decompressed content exceeds the size limit'
        )
    try:
        document = json.loads(decoded.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsersConfigurationValidationError(
            'Users configuration must contain valid UTF-8 JSON'
        ) from error
    if not isinstance(document, dict):
        raise UsersConfigurationValidationError('Users configuration root must be an object')
    return document
