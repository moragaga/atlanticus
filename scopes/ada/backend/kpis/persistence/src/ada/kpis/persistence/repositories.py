from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ada.kpis.core import KpiWatermark
from ada.kpis.persistence.errors import KpiPersistenceCorruptionError
from ada.kpis.persistence.models import KpiEvaluationBatch, KpiEvaluationWriteStatus
from ada.kpis.persistence.paths import KpiPersistencePaths
from atlanticus.json import JsonDocumentStore, JsonWriteOnceStatus


class KpiEvaluationRepository:
    def __init__(
        self,
        *,
        paths: KpiPersistencePaths,
        store: JsonDocumentStore | None = None,
    ) -> None:
        if not isinstance(paths, KpiPersistencePaths):
            raise TypeError('paths must be KpiPersistencePaths')
        self._paths = paths
        self._store = JsonDocumentStore() if store is None else store

    @property
    def paths(self) -> KpiPersistencePaths:
        return self._paths

    def write_once(self, batch: KpiEvaluationBatch) -> KpiEvaluationWriteStatus:
        if not isinstance(batch, KpiEvaluationBatch):
            raise TypeError('batch must be KpiEvaluationBatch')
        status = self._store.write_once(
            self._paths.evaluation_path(batch.watermark),
            batch.to_payload(),
        )
        if status is JsonWriteOnceStatus.CREATED:
            return KpiEvaluationWriteStatus.CREATED
        return KpiEvaluationWriteStatus.UNCHANGED

    def read(self, watermark: KpiWatermark) -> KpiEvaluationBatch | None:
        if not isinstance(watermark, KpiWatermark):
            raise TypeError('watermark must be KpiWatermark')
        payload = self._store.read(self._paths.evaluation_path(watermark))
        if payload is None:
            return None
        batch = KpiEvaluationBatch.from_payload(dict(payload))
        if batch.watermark != watermark:
            raise KpiPersistenceCorruptionError(
                'KPI evaluation batch path does not match payload watermark'
            )
        return batch

    def read_after(
        self,
        *,
        after: KpiWatermark | None,
        through: KpiWatermark,
    ) -> tuple[KpiEvaluationBatch, ...]:
        if after is not None and not isinstance(after, KpiWatermark):
            raise TypeError('after must be KpiWatermark or None')
        if not isinstance(through, KpiWatermark):
            raise TypeError('through must be KpiWatermark')
        if after is not None and after > through:
            raise ValueError('after watermark must not be greater than through watermark')
        if not self._paths.evaluations_root.exists():
            return ()
        batches = []
        for path in sorted(self._paths.evaluations_root.rglob('*.json')):
            path_watermark = _path_watermark(path)
            if after is not None and path_watermark <= after:
                continue
            if path_watermark > through:
                continue
            payload = self._store.read(path)
            if payload is None:
                continue
            batch = KpiEvaluationBatch.from_payload(dict(payload))
            if batch.watermark != path_watermark:
                raise KpiPersistenceCorruptionError(
                    'KPI evaluation batch path does not match payload watermark'
                )
            batches.append(batch)
        batches.sort(key=lambda batch: batch.watermark)
        return tuple(batches)


def _path_watermark(path: Path) -> KpiWatermark:
    try:
        timestamp = datetime.strptime(path.stem, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
    except ValueError as error:
        raise KpiPersistenceCorruptionError(
            f'invalid KPI evaluation batch filename: {path.name}'
        ) from error
    return KpiWatermark(timestamp)
