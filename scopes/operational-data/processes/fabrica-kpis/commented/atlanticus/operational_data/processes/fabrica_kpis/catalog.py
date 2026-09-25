# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
import re

from atlanticus.data_producers.fabrica import FabricaDatasetDefinition, FabricaStreamDefinition

DATASETS = (
    FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=()),
    FabricaDatasetDefinition(name='weekly', source_value='7LD', route_segment='weekly', metrics=()),
)


# Expone únicamente el stream de este proceso con niveles daily y weekly configurables.
def build_catalog() -> FabricaStreamDefinition:
    return FabricaStreamDefinition(
        stream_key='kpis',
        source_prefix='MLP/kpi_fabrica/kpi_fabrica',
        source_filename_pattern=re.compile(
            r'(^|.*/)kpi_fabrica_(?P<file_timestamp>\d{14})\.parquet$'
        ),
        output_route_segment='kpis',
        datasets=DATASETS,
        report_unknown_source_values=False,
    )
