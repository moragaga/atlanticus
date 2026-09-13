from __future__ import annotations

from abc import ABC, abstractmethod

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import RuntimeUserRecord


class UsersRuntimeStore(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord | None:
        raise NotImplementedError

    @abstractmethod
    def observe(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord:
        raise NotImplementedError
