from collections.abc import Sequence
from dash.development.base_component import Component

from ..metrics import FluidMetricReading, build_metric_rows
from .definitions import STA_INDICATORS


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def build_sta(readings: Sequence[FluidMetricReading]) -> Component:
    if len(readings) != len(STA_INDICATORS):
        raise ValueError('STA indicator count is inconsistent')
    return build_metric_rows(readings, class_name='ada-io-sta__indicators')
