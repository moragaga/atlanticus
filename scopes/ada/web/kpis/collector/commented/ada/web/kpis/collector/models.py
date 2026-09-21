# Modelos inmutables del collector. El snapshot conserva marcadores monotónicos para impedir
# que un navegador retroceda al caer en un worker temporalmente más atrasado.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from ada.web.components import ComponentStoreSnapshot


class KpiCollectorError(RuntimeError):
    pass


class KpiCollectorContractError(ValueError):
    pass


class KpiDeliveryReadError(KpiCollectorError):
    pass


class KpiCollectorRefreshStatus(StrEnum):
    UPDATED = 'updated'
    UNCHANGED = 'unchanged'
    MISSING = 'missing'
    STALE = 'stale'
    INCOMPATIBLE = 'incompatible'


@dataclass(frozen=True, slots=True)
class KpiCollectorRefreshResult:
    status: KpiCollectorRefreshStatus
    revision: str | None = None


@dataclass(frozen=True, slots=True)
class ComponentLatestKpiData:
    manifest: Mapping[str, object]
    values: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class ComponentTimeseriesKpiData:
    manifest: Mapping[str, object]
    end_utc: str
    step_seconds: int
    series: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class ComponentKpiData:
    latest: ComponentLatestKpiData | None = None
    timeseries: ComponentTimeseriesKpiData | None = None

    def __post_init__(self) -> None:
        if self.latest is None and self.timeseries is None:
            raise KpiCollectorContractError(
                'Component KPI data requires latest or timeseries delivery data'
            )


@dataclass(frozen=True, slots=True)
class KpiCollectorSnapshot:
    stores: tuple[ComponentStoreSnapshot, ...]
    latest_revision: str | None = None
    latest_watermark_utc: str | None = None
    latest_configuration_revision: str | None = None
    timeseries_revision: str | None = None
    timeseries_end_utc: str | None = None
    timeseries_configuration_revision: str | None = None

    @property
    def has_delivery_data(self) -> bool:
        return self.latest_revision is not None or self.timeseries_revision is not None

    @property
    def browser_revision(self) -> dict[str, object | None]:
        latest = None
        if self.latest_revision is not None:
            latest = {
                'revision': self.latest_revision,
                'watermark_utc': self.latest_watermark_utc,
                'configuration_revision': self.latest_configuration_revision,
            }
        timeseries = None
        if self.timeseries_revision is not None:
            timeseries = {
                'revision': self.timeseries_revision,
                'end_utc': self.timeseries_end_utc,
                'configuration_revision': self.timeseries_configuration_revision,
            }
        return {'latest': latest, 'timeseries': timeseries}


class KpiDeliveryReader(Protocol):
    def read_latest(self) -> Mapping[str, Any] | None: ...

    def read_timeseries(self) -> Mapping[str, Any] | None: ...
