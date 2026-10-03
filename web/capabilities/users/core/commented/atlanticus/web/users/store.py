from __future__ import annotations

# Cada frontera durable tiene su store explícito; runtime no administra identidad global.

from abc import ABC, abstractmethod

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import (
    DiscoveredUser,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)


class UsersRuntimeStore(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUser | None:
        raise NotImplementedError

    @abstractmethod
    def list_users(self) -> tuple[RuntimeUser, ...]:
        raise NotImplementedError

    @abstractmethod
    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]:
        raise NotImplementedError


class UsersRegistryStore(ABC):
    @abstractmethod
    def load(self) -> UsersRegistrySnapshot:
        raise NotImplementedError

    @abstractmethod
    def replace(
        self,
        users: tuple[UserIdentity, ...],
        *,
        expected_version: str | None,
    ) -> UsersRegistrySnapshot:
        raise NotImplementedError


class ToolMembershipStore(ABC):
    @abstractmethod
    def load(self) -> ToolMembershipSnapshot:
        raise NotImplementedError

    @abstractmethod
    def replace(
        self,
        memberships: tuple[ToolUserMembership, ...],
        *,
        expected_version: str | None,
    ) -> ToolMembershipSnapshot:
        raise NotImplementedError


class UsersDirectoryReader(ABC):
    @abstractmethod
    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        raise NotImplementedError
