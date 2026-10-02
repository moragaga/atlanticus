from __future__ import annotations

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiDeliveryCheckpoint
from atlanticus.state import AtomicStateStore, StateKey

_CHECKPOINT_KEY = StateKey(namespace=('kpi-delivery',), name='checkpoint')


class KpiLatestDeliveryCheckpointStore:
    def __init__(self, *, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    def read(self) -> KpiDeliveryCheckpoint | None:
        document = self._store.read(_CHECKPOINT_KEY)
        if document is None:
            return None
        if set(document.value) != {'watermark_utc', 'configuration_revision'}:
            raise KpiDeliveryRepositoryError('KPI delivery checkpoint has unexpected fields')
        raw_watermark = document.value.get('watermark_utc')
        if not isinstance(raw_watermark, str):
            raise KpiDeliveryRepositoryError('KPI delivery checkpoint watermark is invalid')
        try:
            watermark = KpiWatermark.from_text(raw_watermark)
        except (TypeError, ValueError) as error:
            raise KpiDeliveryRepositoryError(
                'KPI delivery checkpoint watermark is invalid'
            ) from error
        revision = document.value.get('configuration_revision')
        if not isinstance(revision, str):
            raise KpiDeliveryRepositoryError(
                'KPI delivery checkpoint configuration_revision is invalid'
            )
        return KpiDeliveryCheckpoint(
            watermark=watermark,
            configuration_revision=revision,
        )

    def commit(self, checkpoint: KpiDeliveryCheckpoint) -> KpiDeliveryCheckpoint:
        if not isinstance(checkpoint, KpiDeliveryCheckpoint):
            raise TypeError('checkpoint must be KpiDeliveryCheckpoint')
        current = self.read()
        if current is not None and checkpoint.watermark < current.watermark:
            raise KpiDeliveryRepositoryError('KPI delivery checkpoint watermark must not regress')
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
