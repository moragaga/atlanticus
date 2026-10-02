# Espejo pedagógico: explica el orden durable batch→watermark y la idempotencia sin alterar la semántica.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ada.kpis.core import KpiWatermark


@dataclass(frozen=True, slots=True)
class KpiPersistencePaths:
    application_root: Path

    def __post_init__(self) -> None:
        root = Path(self.application_root)
        if not root.is_absolute():
            raise ValueError('KPI application_root must be absolute')
        object.__setattr__(self, 'application_root', root)

    @property
    def evaluations_root(self) -> Path:
        return self.application_root / 'datasets' / 'kpis' / 'evaluations'

    def evaluation_path(self, watermark: KpiWatermark) -> Path:
        timestamp = watermark.timestamp_utc
        name = timestamp.strftime('%Y%m%dT%H%M%SZ.json')
        return (
            self.evaluations_root
            / f'year={timestamp:%Y}'
            / f'month={timestamp:%m}'
            / f'day={timestamp:%d}'
            / f'hour={timestamp:%H}'
            / name
        )
