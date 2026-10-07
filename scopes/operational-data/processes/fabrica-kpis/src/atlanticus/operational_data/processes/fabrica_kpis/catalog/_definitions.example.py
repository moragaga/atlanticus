from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    FabricaValueKind,
)

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
        partition_dimensions=('year', 'month'),
    ),
)
