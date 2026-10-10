from ..indicators import FluidMetricDefinition

# Se conservan las dos filas originales de Tranque.
TRANQUE_INDICATORS = (
    FluidMetricDefinition('Arenas Prod Día', 'produccion_arenas_real_acc_dia', 'kt'),
    FluidMetricDefinition('Cp Descarga', 'cp_descarga_real_mean_hora', '%'),
)
