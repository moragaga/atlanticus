from __future__ import annotations

import importlib

import pytest

from atlanticus.integrations.pi.contracts import PiExtractionMode
from atlanticus.runtime import JOB_EXECUTION_DISABLED_VARIABLE

_MODULES = (
    'atlanticus.operational_data.processes.blockgrade.settings',
    'atlanticus.operational_data.processes.dispatch.settings',
    'atlanticus.operational_data.processes.fabrica_kpis.settings',
    'atlanticus.operational_data.processes.fabrica_planes.settings',
    'atlanticus.operational_data.processes.meteodata.settings',
    'atlanticus.operational_data.processes.notpii.settings',
    'atlanticus.operational_data.processes.pi.settings',
    'atlanticus.operational_data.processes.remanentes.settings',
)


@pytest.mark.parametrize('module_name', _MODULES)
def test_process_configuration_preserves_execution_disabled_signal(module_name: str) -> None:
    module = importlib.import_module(module_name)
    if module_name == 'atlanticus.operational_data.processes.notpii.settings':
        specs = {
            spec.key: spec
            for spec in module.configuration_specs(
                active_modes=(
                    PiExtractionMode.INTERPOLATED,
                    PiExtractionMode.RECORDED,
                )
            )
        }
    else:
        specs = {spec.key: spec for spec in module.configuration_specs()}

    assert specs[JOB_EXECUTION_DISABLED_VARIABLE].default == 'false'
