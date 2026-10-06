# Espejo pedagógico del catálogo de ejemplo de Fábrica KPIs.
# Este archivo no participa del catálogo productivo; definitions.py permanece independiente.
# Las métricas usan nombres EXAMPLE_* para dejar explícito que no representan KPIs reales.
from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    FabricaValueKind,
)

# Una definición de métrica puede reutilizarse en más de un dataset siempre que conserve
# exactamente el mismo id_kpi, metric_key y value_kind.
EXAMPLE_KPI_METRICS = (
    FabricaMetricDefinition(
        id_kpi='EXAMPLE_PRODUCTION_RATE',
        metric_key='example_production_rate',
        value_kind=FabricaValueKind.FLOAT,
    ),
    FabricaMetricDefinition(
        id_kpi='EXAMPLE_OPERATING_STATE',
        metric_key='example_operating_state',
        value_kind=FabricaValueKind.BOOLEAN,
    ),
)

# Daily conserva la partición year/month propia del proceso de KPIs.
# Weekly mantiene el contrato vigente sin particiones adicionales.
EXAMPLE_DATASETS = (
    FabricaDatasetDefinition(
        name='daily',
        source_value='DAY',
        route_segment='daily',
        metrics=EXAMPLE_KPI_METRICS,
        partition_dimensions=('year', 'month'),
    ),
    FabricaDatasetDefinition(
        name='weekly',
        source_value='7LD',
        route_segment='weekly',
        metrics=EXAMPLE_KPI_METRICS,
    ),
)
