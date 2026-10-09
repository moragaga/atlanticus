# Claves iniciales tomadas de la referencia legacy; el color opcional no altera la lectura del valor.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CorreaStmgDefinition:
    label: str
    state_kpi_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Correa STMG label must be a non-empty string')
        if not isinstance(self.state_kpi_key, str) or not self.state_kpi_key.strip():
            raise ValueError('Correa STMG state_kpi_key must be a non-empty string')


@dataclass(frozen=True, slots=True)
class CorreaStmgMetricDefinition:
    label: str
    value_kpi_key: str
    color_kpi_key: str | None = None
    unit: str = 'TPH'

    def __post_init__(self) -> None:
        for name in ('label', 'value_kpi_key', 'unit'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Correa STMG {name} must be a non-empty string')
        if self.color_kpi_key is not None:
            if not isinstance(self.color_kpi_key, str) or not self.color_kpi_key.strip():
                raise ValueError('Correa STMG color_kpi_key must be null or a non-empty string')
            if self.color_kpi_key == self.value_kpi_key:
                raise ValueError('Correa STMG value and color KPI keys must be distinct')


CORREAS_STMG_DEFINITIONS = (
    CorreaStmgDefinition('CV005', 'estado_correa_005_inst'),
    CorreaStmgDefinition('CV006', 'estado_correa_006_inst'),
    CorreaStmgDefinition('CV007', 'estado_correa_007_inst'),
)

CORREAS_STMG_METRIC = CorreaStmgMetricDefinition(
    label='Transp. STMG',
    value_kpi_key='transportado_stmg_inst',
)
