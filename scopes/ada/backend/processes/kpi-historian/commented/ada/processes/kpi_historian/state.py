# Adaptador de estado que materializa la autoridad compartida declarada por ada.kpis.history.
from __future__ import annotations

from ada.kpis.history import (
    HISTORIAN_AUTHORITY_NAME,
    HISTORIAN_AUTHORITY_NAMESPACE,
    KpiHistorianAuthority,
    KpiHistoryContractError,
)
from ada.processes.kpi_historian.errors import KpiHistorianRepositoryError
from atlanticus.state import AtomicStateStore, StateKey

_AUTHORITY_KEY = StateKey(
    namespace=HISTORIAN_AUTHORITY_NAMESPACE,
    name=HISTORIAN_AUTHORITY_NAME,
)


class KpiHistorianAuthorityStore:
    def __init__(self, *, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    def read(self) -> KpiHistorianAuthority | None:
        document = self._store.read(_AUTHORITY_KEY)
        if document is None:
            return None
        try:
            return KpiHistorianAuthority.from_payload(document.value)
        except (TypeError, ValueError, KpiHistoryContractError) as error:
            raise KpiHistorianRepositoryError('KPI historian authority state is invalid') from error

    def commit(self, authority: KpiHistorianAuthority) -> KpiHistorianAuthority:
        if not isinstance(authority, KpiHistorianAuthority):
            raise TypeError('authority must be KpiHistorianAuthority')
        current = self.read()
        if current is not None and authority.watermark_utc < current.watermark_utc:
            raise KpiHistorianRepositoryError('KPI historian authority watermark must not regress')
        if current == authority:
            return current
        self._store.replace(_AUTHORITY_KEY, authority.to_payload())
        return authority
