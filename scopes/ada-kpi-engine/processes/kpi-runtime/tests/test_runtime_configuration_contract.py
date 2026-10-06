from __future__ import annotations

import importlib

import pytest

from atlanticus.runtime import JOB_EXECUTION_DISABLED_VARIABLE

_MODULES = (
    'ada.processes.kpi_delivery.settings',
    'ada.processes.kpi_historian.settings',
    'ada.processes.kpi_materialization.settings',
    'ada.processes.kpi_runtime.settings',
    'ada.processes.kpi_timeseries_delivery.settings',
)


@pytest.mark.parametrize('module_name', _MODULES)
def test_process_configuration_preserves_execution_disabled_signal(module_name: str) -> None:
    module = importlib.import_module(module_name)
    specs = {spec.key: spec for spec in module.configuration_specs()}

    assert specs[JOB_EXECUTION_DISABLED_VARIABLE].default == 'false'
