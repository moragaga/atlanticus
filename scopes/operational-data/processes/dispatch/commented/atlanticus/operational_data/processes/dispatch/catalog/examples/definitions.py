# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
from atlanticus.operational_data.processes.dispatch.catalog.examples.tables import (
    shift_info,
    std_shift_dumps,
    std_shift_dumps_nodica,
    std_shift_grade,
    std_shift_loads,
    std_shift_loads_2,
    std_shift_loads_2_nodica,
    std_shift_state,
    std_truck,
    tiempos_mlp,
)

EXAMPLE_DEFINITIONS = (
    tiempos_mlp.DEFINITION,
    shift_info.DEFINITION,
    std_shift_state.DEFINITION,
    std_shift_loads.DEFINITION,
    std_shift_loads_2.DEFINITION,
    std_shift_dumps.DEFINITION,
    std_shift_dumps_nodica.DEFINITION,
    std_shift_loads_2_nodica.DEFINITION,
    std_shift_grade.DEFINITION,
    std_truck.DEFINITION,
)
