# Espejo pedagógico de Latest Delivery multi-Tool: state.py.
from __future__ import annotations

from ada.kpis.materialization import require_tool_key
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiDeliveryCheckpoint
from atlanticus.state import AtomicStateStore, StateError, StateKey


# Agrupa una responsabilidad con estado o contrato propio.
class KpiLatestDeliveryCheckpointStore:
    def __init__(self, *, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    def read(self, tool_key: str) -> KpiDeliveryCheckpoint | None:
        resolved_tool_key = require_tool_key(tool_key)
        try:
            document = self._store.read(_checkpoint_key(resolved_tool_key))
        except StateError as error:
            raise KpiDeliveryRepositoryError(
                f'Could not read KPI delivery checkpoint for {resolved_tool_key}'
            ) from error
        if document is None:
            return None
        if set(document.value) != {
            'watermark_utc',
            'registry_revision',
            'registry_digest',
        }:
            raise KpiDeliveryRepositoryError(
                f'KPI delivery checkpoint has unexpected fields for {resolved_tool_key}'
            )
        try:
            return KpiDeliveryCheckpoint(
                watermark=_watermark(document.value.get('watermark_utc')),
                registry_revision=_text(
                    document.value.get('registry_revision'),
                    'registry_revision',
                ),
                registry_digest=_text(
                    document.value.get('registry_digest'),
                    'registry_digest',
                ),
            )
        except (TypeError, ValueError) as error:
            raise KpiDeliveryRepositoryError(
                f'KPI delivery checkpoint is invalid for {resolved_tool_key}'
            ) from error

    def commit(
        self,
        tool_key: str,
        checkpoint: KpiDeliveryCheckpoint,
    ) -> KpiDeliveryCheckpoint:
        resolved_tool_key = require_tool_key(tool_key)
        if not isinstance(checkpoint, KpiDeliveryCheckpoint):
            raise TypeError('checkpoint must be KpiDeliveryCheckpoint')
        current = self.read(resolved_tool_key)
        if current is not None and checkpoint.watermark < current.watermark:
            raise KpiDeliveryRepositoryError(
                f'KPI delivery checkpoint watermark must not regress for {resolved_tool_key}'
            )
        if current == checkpoint:
            return current
        try:
            self._store.replace(
                _checkpoint_key(resolved_tool_key),
                {
                    'watermark_utc': checkpoint.watermark.to_text(),
                    'registry_revision': checkpoint.registry_revision,
                    'registry_digest': checkpoint.registry_digest,
                },
            )
        except StateError as error:
            raise KpiDeliveryRepositoryError(
                f'Could not write KPI delivery checkpoint for {resolved_tool_key}'
            ) from error
        return checkpoint


# Expone una operación manteniendo validación explícita.
def _checkpoint_key(tool_key: str) -> StateKey:
    return StateKey(
        namespace=('kpi-delivery', 'tools', tool_key),
        name='checkpoint',
    )


# Expone una operación manteniendo validación explícita.
def _watermark(value: object):
    if not isinstance(value, str):
        raise KpiDeliveryRepositoryError('checkpoint watermark_utc must be text')
    from ada.kpis.core import KpiWatermark

    return KpiWatermark.from_text(value)


# Expone una operación manteniendo validación explícita.
def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KpiDeliveryRepositoryError(
            f'checkpoint {field_name} must be non-empty trimmed text'
        )
    return value
