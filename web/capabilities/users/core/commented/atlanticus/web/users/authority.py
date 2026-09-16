from __future__ import annotations

# Users define una autoridad mínima propia para poder ejecutarse sin instalar Profiles.
# guest y local son reservadas; basic y root son asignables; sólo root y local tienen acceso total.
# La normalización pertenece a Users y evita depender de validadores visuales del dominio Profiles.


import re

from atlanticus.web.users.errors import UsersDefinitionError

GUEST_AUTHORITY_KEY = 'guest'
BASIC_AUTHORITY_KEY = 'basic'
ROOT_AUTHORITY_KEY = 'root'
LOCAL_AUTHORITY_KEY = 'local'

GUEST_BACKGROUND_COLOR = '#FF5722'
GUEST_TEXT_COLOR = '#FFFFFF'
LOCAL_JANE_BACKGROUND_COLOR = '#C85D91'
LOCAL_JANE_TEXT_COLOR = '#FFFFFF'
LOCAL_JOHN_BACKGROUND_COLOR = '#3778C2'
LOCAL_JOHN_TEXT_COLOR = '#FFFFFF'

BASE_AUTHORITY_KEYS = frozenset(
    {
        GUEST_AUTHORITY_KEY,
        BASIC_AUTHORITY_KEY,
        ROOT_AUTHORITY_KEY,
        LOCAL_AUTHORITY_KEY,
    }
)
_NON_ASSIGNABLE_AUTHORITY_KEYS = frozenset(
    {
        GUEST_AUTHORITY_KEY,
        LOCAL_AUTHORITY_KEY,
    }
)
_FULL_ACCESS_AUTHORITY_KEYS = frozenset(
    {
        ROOT_AUTHORITY_KEY,
        LOCAL_AUTHORITY_KEY,
    }
)
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def normalize_authority_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        raise UsersDefinitionError('User authority key must not be empty')
    if any(character.isspace() for character in normalized):
        raise UsersDefinitionError('User authority key must not contain spaces')
    return normalized


def is_assignable_authority(authority_key: str) -> bool:
    return normalize_authority_key(authority_key) not in _NON_ASSIGNABLE_AUTHORITY_KEYS


def has_full_access(authority_key: str) -> bool:
    return normalize_authority_key(authority_key) in _FULL_ACCESS_AUTHORITY_KEYS


def normalize_user_color(value: str) -> str:
    normalized = value.strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise UsersDefinitionError('User color must use #RRGGBB format')
    return normalized
