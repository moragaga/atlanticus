# Orquesta una única resolución Identity -> AccessResolver por carga de página.
# El load_id se crea antes de resolver Users para que todas las capacidades
# puedan asociar sus snapshots a la misma carga.

from __future__ import annotations

from flask import Request

from atlanticus.web.identity.access import (
    AccessResolver,
    AccessRuntime,
    AccessSnapshot,
    new_access_load_id,
)
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.provider import IdentityProvider


class AccessBootstrap:
    def __init__(
        self,
        *,
        provider: IdentityProvider,
        resolver: AccessResolver,
        runtime: AccessRuntime,
    ) -> None:
        self._provider = provider
        self._resolver = resolver
        self._runtime = runtime

    def refresh(self, request: Request) -> AccessSnapshot:
        try:
            self._runtime.clear()
            identity = self._provider.resolve(request)
        except IdentityAuthenticationError:
            snapshot = AccessSnapshot.invalid_identity()
            self._runtime.store(snapshot)
            return snapshot

        load_id = new_access_load_id()
        decision = self._resolver.resolve(identity, load_id=load_id)
        snapshot = AccessSnapshot.resolved(
            load_id=load_id,
            identity=identity,
            decision=decision,
        )
        self._runtime.store(snapshot)
        return snapshot
