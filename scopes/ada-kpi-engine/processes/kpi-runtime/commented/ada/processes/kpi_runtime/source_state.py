from __future__ import annotations

# Espejo pedagógico: conserva exactamente la semántica productiva y explica el contrato temporal.
from collections.abc import Mapping
from datetime import UTC, datetime

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_runtime.errors import KpiRuntimeSourceStateError
from atlanticus.operational_data.sources import PiSourceProvider
from atlanticus.state import AtomicStateStore, StateKey


class PiOperationalWatermarkReader:
    def __init__(self, *, store: AtomicStateStore, provider: PiSourceProvider) -> None:
        if not isinstance(store, AtomicStateStore):
            raise TypeError('store must be an AtomicStateStore')
        if not isinstance(provider, PiSourceProvider):
            raise TypeError('provider must be PiSourceProvider')
        self._store = store
        self._provider = provider

    def current(self) -> KpiWatermark | None:
        # El runtime consume una sola autoridad temporal operacional por proveedor.
        if self._provider is PiSourceProvider.PI_WEB_API:
            return self._read_pi_web_api()
        return self._read_notpii()

    def _read_pi_web_api(self) -> KpiWatermark | None:
        # PI Web API ya publica el último slot interpolado cerrado y materializado.
        document = self._store.read(StateKey(namespace=('sources',), name='pi-web-api'))
        if document is None:
            return None
        value = document.value
        if set(value) != {'source', 'source_watermark_utc'}:
            raise KpiRuntimeSourceStateError(
                'PI Web API source state has unexpected or missing fields'
            )
        if value.get('source') != 'pi-web-api':
            raise KpiRuntimeSourceStateError('PI Web API source state has an invalid source')
        return _watermark(value.get('source_watermark_utc'), source='PI Web API')

    def _read_notpii(self) -> KpiWatermark | None:
        # NOTPII mantiene un máximo global entre streams, pero ese máximo no es el reloj KPI.
        document = self._store.read(StateKey(namespace=('producers',), name='notpii'))
        if document is None:
            return None
        value = document.value
        if value.get('producer') != 'notpii':
            raise KpiRuntimeSourceStateError('NOT PII producer state has an invalid producer')
        streams = value.get('streams')
        if not isinstance(streams, Mapping):
            raise KpiRuntimeSourceStateError('NOT PII producer state streams must be a mapping')
        # La fuente de verdad temporal es exclusivamente el stream interpolated conciliado.
        interpolated = streams.get('interpolated')
        if interpolated is None:
            return None
        if not isinstance(interpolated, Mapping):
            raise KpiRuntimeSourceStateError('NOT PII interpolated stream state must be a mapping')
        if 'source_watermark_utc' not in interpolated:
            raise KpiRuntimeSourceStateError(
                'NOT PII interpolated stream state is missing the source watermark contract'
            )
        return _watermark(
            interpolated.get('source_watermark_utc'),
            source='NOT PII interpolated',
        )


def _watermark(value: object, *, source: str) -> KpiWatermark | None:
    # KPI Runtime valida el watermark publicado, pero no vuelve a normalizar la granularidad del productor.
    if value is None:
        return None
    if not isinstance(value, str):
        raise KpiRuntimeSourceStateError(f'{source} source watermark must be text or null')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise KpiRuntimeSourceStateError(f'{source} source watermark is invalid') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KpiRuntimeSourceStateError(f'{source} source watermark must be timezone-aware')
    try:
        return KpiWatermark(parsed.astimezone(UTC))
    except ValueError as error:
        raise KpiRuntimeSourceStateError(f'{source} source watermark is invalid') from error
