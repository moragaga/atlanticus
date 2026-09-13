from __future__ import annotations

from abc import ABC, abstractmethod

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import RuntimeUserRecord


# El store runtime es la única frontera para consultar y observar el ciclo de vida durable.
# resolve no crea estado; observe crea Pending sólo si la identidad sigue ABSENT y debe ser atómico.
class UsersRuntimeStore(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord | None:
        raise NotImplementedError

    # Si otra operación promovió o deshabilitó al usuario concurrentemente,
    # observe devuelve ese estado Managed y nunca lo degrada de nuevo a Pending.
    @abstractmethod
    def observe(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord:
        raise NotImplementedError
