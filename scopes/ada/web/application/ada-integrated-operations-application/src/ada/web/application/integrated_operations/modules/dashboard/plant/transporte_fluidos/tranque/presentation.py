from collections.abc import Sequence

from dash.development.base_component import Component

from ..indicators import FluidMetricReading, build_metric_rows
from .definitions import TRANQUE_INDICATORS


def build_tranque(readings: Sequence[FluidMetricReading]) -> Component:
    if len(readings) != len(TRANQUE_INDICATORS):
        raise ValueError('TRANQUE indicator count is inconsistent')
    return build_metric_rows(readings, class_name='ada-io-tranque__indicators')
