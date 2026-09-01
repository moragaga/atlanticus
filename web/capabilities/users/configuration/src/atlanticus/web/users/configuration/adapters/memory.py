from __future__ import annotations

from dataclasses import dataclass, field

from atlanticus.web.users.configuration.bundle import (
    UsersConfigurationBundle,
    UsersConfigurationSourceDocument,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationSourceError
from atlanticus.web.users.configuration.models import DiscoveredUser
from atlanticus.web.users.configuration.projection import UsersProjectionState


@dataclass(slots=True)
class MemoryUsersConfigurationStore:
    source: UsersConfigurationSourceDocument | None = None

    def fetch_bundle(self) -> UsersConfigurationBundle | None:
        return self.source.current_bundle() if self.source is not None else None

    def publish_bundle(
        self,
        bundle: UsersConfigurationBundle,
        *,
        expected_source_revision: str | None,
    ) -> None:
        current = self.fetch_bundle()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise UsersConfigurationSourceError('Users source revision changed before publication')
        if self.source is None:
            self.source = UsersConfigurationSourceDocument.from_bundle(bundle)
            return
        self.source = self.source.publish(bundle)

    def list_history(self, *, limit: int = 20) -> tuple[UsersConfigurationBundle, ...]:
        return self.source.list_history(limit=limit) if self.source is not None else ()

    def fetch_revision(self, revision: str) -> UsersConfigurationBundle | None:
        return self.source.fetch_revision(revision) if self.source is not None else None


@dataclass(slots=True)
class MemoryUsersProjectionRepository:
    state: UsersProjectionState | None = None
    last_bundle: UsersConfigurationBundle | None = None

    def load_state(self) -> UsersProjectionState | None:
        return self.state

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState:
        self.last_bundle = bundle
        self.state = UsersProjectionState.create(
            source_revision=bundle.revision,
            projected_by=actor,
        )
        return self.state

    def health_check(self) -> bool:
        return True


@dataclass(slots=True)
class MemoryDiscoveredUsersSource:
    users: list[DiscoveredUser] = field(default_factory=list)

    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        return tuple(self.users)
