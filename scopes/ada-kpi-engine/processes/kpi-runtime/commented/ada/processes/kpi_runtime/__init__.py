# Espejo pedagógico: conserva el comportamiento productivo y documenta la responsabilidad de este módulo.
from ada.processes.kpi_runtime.bootstrap import load_configuration, run
from ada.processes.kpi_runtime.catalog import build_catalog
from ada.processes.kpi_runtime.composition import KpiRuntimeComposition, build_composition
from ada.processes.kpi_runtime.errors import (
    KpiRuntimeConfigurationError,
    KpiRuntimeDataError,
    KpiRuntimeError,
    KpiRuntimeSourceStateError,
    KpiRuntimeWatermarkError,
)
from ada.processes.kpi_runtime.job import KpiRuntimeJob
from ada.processes.kpi_runtime.models import KpiRuntimeIterationResult, KpiRuntimeOutcome
from ada.processes.kpi_runtime.reader import RoutedDatasetSourceReader
from ada.processes.kpi_runtime.settings import KpiRuntimeSettings, configuration_specs
from ada.processes.kpi_runtime.source_state import PiOperationalWatermarkReader

__version__ = '1.0.0'

__all__ = [
    'KpiRuntimeComposition',
    'KpiRuntimeConfigurationError',
    'KpiRuntimeDataError',
    'KpiRuntimeError',
    'KpiRuntimeIterationResult',
    'KpiRuntimeJob',
    'KpiRuntimeOutcome',
    'KpiRuntimeSettings',
    'KpiRuntimeSourceStateError',
    'KpiRuntimeWatermarkError',
    'PiOperationalWatermarkReader',
    'RoutedDatasetSourceReader',
    '__version__',
    'build_catalog',
    'build_composition',
    'configuration_specs',
    'load_configuration',
    'run',
]
