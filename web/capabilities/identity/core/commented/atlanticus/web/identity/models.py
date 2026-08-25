# AuthenticatedIdentity contiene solo evidencia normalizada recibida del provider.
from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.identity.errors import IdentityDefinitionError


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    provider_key: str
    issuer: str
    subject_id: str
    display_name: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        for field_name in ('provider_key', 'issuer', 'subject_id'):
            value = getattr(self, field_name).strip()
            if not value:
                raise IdentityDefinitionError(f'Identity {field_name} must not be empty')
            object.__setattr__(self, field_name, value)

        for field_name in ('display_name', 'email'):
            value = getattr(self, field_name)
            if value is not None:
                normalized = value.strip()
                object.__setattr__(self, field_name, normalized or None)
