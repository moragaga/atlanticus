# Espejo pedagógico de KPI Materialization migrado al contrato compartido: __init__.py.
from ada.processes.kpi_materialization.bootstrap import (
    load_configuration,
    run,
)
from ada.processes.kpi_materialization.job import (
    KpiMaterializationIterationResult,
    KpiMaterializationJob,
)

__version__ = '1.0.0'

__all__ = [
    'KpiMaterializationIterationResult',
    'KpiMaterializationJob',
    'load_configuration',
    'run',
    '__version__',
]
