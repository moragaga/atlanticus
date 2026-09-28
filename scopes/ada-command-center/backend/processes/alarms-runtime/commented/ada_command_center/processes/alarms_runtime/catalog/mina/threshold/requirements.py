# Declaración manual de datos: no consulta ni interpreta parámetros de la Web.
# La tupla puede contener varios DataRequirement de fuentes o particiones distintas.

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    TimeWindow,
    TimeWindowUnit,
)

THRESHOLD_REQUIREMENTS = (
    DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.DAILY,
        columns=(DataColumn('temperature', DataColumnType.FLOAT),),
        time_window=TimeWindow(4, TimeWindowUnit.HOURS),
    ),
)
