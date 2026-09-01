# Espejo comentado de la implementación productiva.
from __future__ import annotations

from ada.kpis.core import KpiWatermark
from ada.kpis.history import (
    HISTORIAN_AUTHORITY_NAME,
    HISTORIAN_AUTHORITY_NAMESPACE,
    KpiHistorianAuthority,
    KpiHistoryContractError,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesCheckpoint
from atlanticus.state import AtomicStateStore, StateKey

_AUTHORITY_KEY = StateKey(
    namespace=HISTORIAN_AUTHORITY_NAMESPACE,
    name=HISTORIAN_AUTHORITY_NAME,
)
_CHECKPOINT_KEY = StateKey(namespace=('kpi-timeseries-delivery',), name='checkpoint')


class KpiHistorianAuthorityReader:
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
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI historian authority state is invalid'
            ) from error


class KpiTimeseriesDeliveryCheckpointStore:
    def __init__(self, *, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    def read(self) -> KpiTimeseriesCheckpoint | None:
        document = self._store.read(_CHECKPOINT_KEY)
        if document is None:
            return None
        if set(document.value) != {'watermark_utc', 'configuration_revision'}:
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI timeseries delivery checkpoint has unexpected fields'
            )
        raw_watermark = document.value.get('watermark_utc')
        revision = document.value.get('configuration_revision')
        if not isinstance(raw_watermark, str):
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI timeseries delivery checkpoint watermark is invalid'
            )
        if not isinstance(revision, str):
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI timeseries delivery checkpoint configuration_revision is invalid'
            )
        try:
            watermark = KpiWatermark.from_text(raw_watermark)
        except (TypeError, ValueError) as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI timeseries delivery checkpoint watermark is invalid'
            ) from error
        return KpiTimeseriesCheckpoint(
            watermark=watermark,
            configuration_revision=revision,
        )

    def commit(self, checkpoint: KpiTimeseriesCheckpoint) -> KpiTimeseriesCheckpoint:
        if not isinstance(checkpoint, KpiTimeseriesCheckpoint):
            raise TypeError('checkpoint must be KpiTimeseriesCheckpoint')
        current = self.read()
        if current is not None and checkpoint.watermark < current.watermark:
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI timeseries delivery checkpoint watermark must not regress'
            )
        if current == checkpoint:
            return current
        self._store.replace(
            _CHECKPOINT_KEY,
            {
                'watermark_utc': checkpoint.watermark.to_text(),
                'configuration_revision': checkpoint.configuration_revision,
            },
        )
        return checkpoint
