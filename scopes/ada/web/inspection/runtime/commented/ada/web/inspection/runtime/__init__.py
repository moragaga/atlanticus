# Expone los dos puntos explícitos de lifecycle; el host decide cuándo ejecutar warmup y cuándo programar refresh.
from ada.web.inspection.runtime.lifecycle import KpiDefinitionRefresh, KpiDefinitionWarmup

__all__ = ['KpiDefinitionRefresh', 'KpiDefinitionWarmup']
