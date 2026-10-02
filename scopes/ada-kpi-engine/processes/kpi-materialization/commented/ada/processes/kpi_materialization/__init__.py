# Espejo pedagógico del proceso KPI Materialization: __init__.py.
from ada.processes.kpi_materialization.bootstrap import (
    load_configuration,
    run,
)
from ada.processes.kpi_materialization.connections import (
    CosmosConnectionDeclaration,
    KpiMaterializationConnectionRegistry,
    read_connection_registry,
)
from ada.processes.kpi_materialization.job import (
    KpiMaterializationIterationResult,
    KpiMaterializationJob,
)

__version__ = '1.0.0'

__all__ = [
    'CosmosConnectionDeclaration',
    'KpiMaterializationConnectionRegistry',
    'KpiMaterializationIterationResult',
    'KpiMaterializationJob',
    'load_configuration',
    'read_connection_registry',
    'run',
    '__version__',
]
