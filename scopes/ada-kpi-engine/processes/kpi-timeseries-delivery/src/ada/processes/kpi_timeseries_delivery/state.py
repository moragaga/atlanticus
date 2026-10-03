from __future__ import annotations

from ada.kpis.core import KpiWatermark
from ada.kpis.history import (
    HISTORIAN_AUTHORITY_NAME,
    HISTORIAN_AUTHORITY_NAMESPACE,
    KpiHistorianAuthority,
    KpiHistoryContractError,
)
from ada.kpis.materialization import require_tool_key
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesCheckpoint
from atlanticus.state import AtomicStateStore, StateError, StateKey

_AUTHORITY_KEY = StateKey(
    namespace=HISTORIAN_AUTHORITY_NAMESPACE,
    name=HISTORIAN_AUTHORITY_NAME,
)


class KpiHistorianAuthorityReader:
    def __init__(self, *, store: AtomicStateStore) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be AtomicStateStore')
        self._store = store

    def read(self) -> KpiHistorianAuthority | None:
        try:
            document = self._store.read(_AUTHORITY_KEY)
        except StateError as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                'Could not read KPI historian authority state'
            ) from error
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

    def read(self, tool_key: str) -> KpiTimeseriesCheckpoint | None:
        resolved_tool_key = require_tool_key(tool_key)
        try:
            document = self._store.read(_checkpoint_key(resolved_tool_key))
        except StateError as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                f'Could not read KPI timeseries checkpoint for {resolved_tool_key}'
            ) from error
        if document is None:
            return None
        if set(document.value) != {
            'watermark_utc',
            'registry_revision',
            'registry_digest',
        }:
            raise KpiTimeseriesDeliveryRepositoryError(
                f'KPI timeseries checkpoint has unexpected fields for {resolved_tool_key}'
            )
        try:
            return KpiTimeseriesCheckpoint(
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
            raise KpiTimeseriesDeliveryRepositoryError(
                f'KPI timeseries checkpoint is invalid for {resolved_tool_key}'
            ) from error

    def commit(
        self,
        tool_key: str,
        checkpoint: KpiTimeseriesCheckpoint,
    ) -> KpiTimeseriesCheckpoint:
        resolved_tool_key = require_tool_key(tool_key)
        if not isinstance(checkpoint, KpiTimeseriesCheckpoint):
            raise TypeError('checkpoint must be KpiTimeseriesCheckpoint')
        current = self.read(resolved_tool_key)
        if current is not None and checkpoint.watermark < current.watermark:
            raise KpiTimeseriesDeliveryRepositoryError(
                f'KPI timeseries checkpoint watermark must not regress for {resolved_tool_key}'
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
            raise KpiTimeseriesDeliveryRepositoryError(
                f'Could not write KPI timeseries checkpoint for {resolved_tool_key}'
            ) from error
        return checkpoint


def _checkpoint_key(tool_key: str) -> StateKey:
    return StateKey(
        namespace=('kpi-timeseries-delivery', 'tools', tool_key),
        name='checkpoint',
    )


def _watermark(value: object) -> KpiWatermark:
    if not isinstance(value, str):
        raise KpiTimeseriesDeliveryRepositoryError('checkpoint watermark_utc must be text')
    return KpiWatermark.from_text(value)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KpiTimeseriesDeliveryRepositoryError(
            f'checkpoint {field_name} must be non-empty trimmed text'
        )
    return value
