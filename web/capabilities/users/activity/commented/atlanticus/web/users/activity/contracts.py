# Define primero los puertos consumidos por el core.
# Persistencia y resolución de rutas se inyectan; Activity no crea infraestructura.
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from atlanticus.web.users.activity.errors import UserActivityError
from atlanticus.web.users.activity.models import UserActivityDocument, normalize_pathname


@dataclass(frozen=True, slots=True)
class StoredUserActivity:
    document: UserActivityDocument
    revision: str


class UserActivityRepository(Protocol):
    def load(self, *, document_id: str, partition_key: str) -> StoredUserActivity | None: ...

    def save(
        self,
        document: UserActivityDocument,
        *,
        expected_revision: str | None,
    ) -> StoredUserActivity: ...


@dataclass(frozen=True, slots=True)
class ActivityRoute:
    key: str
    pathname: str

    def __post_init__(self) -> None:
        key = self.key.strip()
        if not key:
            raise UserActivityError('Activity route key must not be empty')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'pathname', normalize_pathname(self.pathname))


class ActivityRouteResolver(Protocol):
    def resolve(self, pathname: str) -> ActivityRoute | None: ...
