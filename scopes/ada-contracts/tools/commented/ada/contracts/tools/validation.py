# Estas funciones normalizan claves y nombres con las mismas reglas del contrato original.
# La lógica se mantiene equivalente al archivo productivo; sólo se agregan comentarios pedagógicos.

import re

from ada.contracts.tools.errors import ToolConfigurationValidationError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def require_key(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ToolConfigurationValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ToolConfigurationValidationError(f'{label} has an invalid format')
    return normalized


def require_display_name(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ToolConfigurationValidationError(f'{label} must be a string')
    normalized = value.strip()
    if not normalized:
        raise ToolConfigurationValidationError(f'{label} must not be empty')
    return normalized
