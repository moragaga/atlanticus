# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
import re

from atlanticus.data_producers.fabrica import FabricaDatasetDefinition, FabricaStreamDefinition

DATASETS = (
    FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=()),
    FabricaDatasetDefinition(name='weekly', source_value='7LDB', route_segment='weekly', metrics=()),
)


# Expone únicamente el stream de este proceso con niveles daily y weekly configurables.
def build_catalog() -> FabricaStreamDefinition:
    return FabricaStreamDefinition(
        stream_key='planes',
        source_prefix='planes_fabrica',
        source_filename_pattern=re.compile(r'(^|.*/)planes_fabrica_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=DATASETS,
        report_unknown_source_values=True,
    )
