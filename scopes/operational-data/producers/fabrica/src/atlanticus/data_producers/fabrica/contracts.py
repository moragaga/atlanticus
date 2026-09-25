from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from atlanticus.data_producers.fabrica.errors import FabricaContractError


class FabricaValueKind(StrEnum):
    FLOAT = 'float'
    INTEGER = 'integer'
    TEXT = 'text'
    BOOLEAN = 'boolean'
    DATETIME = 'datetime'


@dataclass(frozen=True, slots=True)
class FabricaMetricDefinition:
    id_kpi: str
    metric_key: str
    value_kind: FabricaValueKind

    def __post_init__(self) -> None:
        object.__setattr__(self, 'id_kpi', _required_text(self.id_kpi, 'id_kpi').upper())
        object.__setattr__(self, 'metric_key', _route_segment(self.metric_key, 'metric_key'))
        if not isinstance(self.value_kind, FabricaValueKind):
            raise FabricaContractError('value_kind must be a FabricaValueKind')


@dataclass(frozen=True, slots=True)
class FabricaDatasetDefinition:
    name: str
    source_value: str
    route_segment: str
    metrics: tuple[FabricaMetricDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'name', _route_segment(self.name, 'name'))
        object.__setattr__(self, 'source_value', _required_text(self.source_value, 'source_value').upper())
        object.__setattr__(self, 'route_segment', _route_segment(self.route_segment, 'route_segment'))
        metrics = tuple(self.metrics)
        if not all(isinstance(metric, FabricaMetricDefinition) for metric in metrics):
            raise FabricaContractError('metrics must contain FabricaMetricDefinition values')
        _unique(metrics, 'id_kpi', 'dataset metric ids')
        _unique(metrics, 'metric_key', 'dataset metric keys')
        object.__setattr__(self, 'metrics', metrics)


def validate_dataset_catalog(*, datasets: tuple[FabricaDatasetDefinition, ...]) -> None:
    resolved = tuple(datasets)
    if not resolved:
        raise FabricaContractError('datasets must not be empty')
    if not all(isinstance(dataset, FabricaDatasetDefinition) for dataset in resolved):
        raise FabricaContractError('datasets must contain FabricaDatasetDefinition values')
    for field in ('name', 'source_value', 'route_segment'):
        _unique(resolved, field, f'dataset {field} values')
    definitions: dict[str, FabricaMetricDefinition] = {}
    for dataset in resolved:
        for metric in dataset.metrics:
            existing = definitions.setdefault(metric.id_kpi, metric)
            if existing != metric:
                raise FabricaContractError('the same metric id must reuse one definition across datasets')


def _unique(values: tuple[object, ...], field: str, description: str) -> None:
    resolved = tuple(getattr(item, field) for item in values)
    if len(set(resolved)) != len(resolved):
        raise FabricaContractError(f'{description} must be unique')


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FabricaContractError(f'{field} is required')
    return value.strip()


def _route_segment(value: str, field: str) -> str:
    normalized = _required_text(value, field).lower()
    if not normalized.replace('_', '').replace('-', '').isalnum():
        raise FabricaContractError(f'{field} must contain only letters, numbers, hyphens or underscores')
    return normalized
