from __future__ import annotations

from abc import ABC, abstractmethod

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import ResolvedUserRecord


class UsersSource(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity) -> ResolvedUserRecord | None:
        raise NotImplementedError
