# Espejo pedagógico: explica el orden durable batch→watermark y la idempotencia sin alterar la semántica.
from __future__ import annotations

from ada.kpis.persistence.models import KpiCommitState
from atlanticus.state import AtomicStateStore, StateKey

_COMMIT_KEY = StateKey(namespace=('kpis', 'runtime'), name='commit')


class KpiCommitStateRepository:
    def __init__(self, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    @property
    def application_root(self):
        return self._store.application_root

    def read(self) -> KpiCommitState:
        document = self._store.read(_COMMIT_KEY)
        if document is None:
            return KpiCommitState()
        return KpiCommitState.from_payload(dict(document.value))

    def replace(self, state: KpiCommitState) -> KpiCommitState:
        if not isinstance(state, KpiCommitState):
            raise TypeError('state must be KpiCommitState')
        self._store.replace(_COMMIT_KEY, state.to_payload())
        return state
