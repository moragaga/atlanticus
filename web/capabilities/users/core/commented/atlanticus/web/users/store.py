# Espejo pedagógico: conserva exactamente el contrato productivo y explica su intención.
from __future__ import annotations

from abc import ABC, abstractmethod

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import DiscoveredUser, UserRecord, UsersRegistrySnapshot


class UsersRuntimeStore(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity) -> UserRecord | None:
        raise NotImplementedError


class UsersAdministrationStore(ABC):
    @abstractmethod
    def get(self, user_id: str) -> UserRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_users(self) -> tuple[UserRecord, ...]:
        raise NotImplementedError

    @abstractmethod
    def create(self, user: UserRecord) -> UserRecord:
        raise NotImplementedError

    @abstractmethod
    def replace(self, user: UserRecord) -> UserRecord:
        raise NotImplementedError


class UsersRegistryStore(ABC):
    @abstractmethod
    def load(self) -> UsersRegistrySnapshot:
        raise NotImplementedError

    @abstractmethod
    def replace(
        self,
        users: tuple[UserRecord, ...],
        *,
        expected_version: str | None,
    ) -> UsersRegistrySnapshot:
        raise NotImplementedError


class UsersDirectoryReader(ABC):
    @abstractmethod
    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        raise NotImplementedError
