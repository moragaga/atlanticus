from ..indicators import FluidMetricDefinition

# Orden y nombres de los KPI históricos permanecen iguales.
STA_INDICATORS = (
    FluidMetricDefinition('Make Up', 'make_up_real_mean_hora', 'm³/t'),
    FluidMetricDefinition('Flujo R2', 'flujo_r2_real_mean_hora', 'l/s'),
    FluidMetricDefinition('Capt Agua', 'captacion_agua_real_mean_hora', 'lts'),
    FluidMetricDefinition('DB TK52', 'disponibilidad_bombas_tk52_real', '%'),
    FluidMetricDefinition('Batimetría', 'batimetria_real_mean_hora', 'Mm³'),
    FluidMetricDefinition('Norte', 'nivel_piscina_norte_real_mean_hora', '%'),
    FluidMetricDefinition('Sur', 'nivel_piscina_sur_real_mean_hora', '%'),
    FluidMetricDefinition('N.Norte', 'nivel_piscina_norte_norte_real_mean_hora', '%'),
)
