from .bindings import DashboardGlobalIndicatorBinding

# Catálogo productivo único de Global Indicators para Operaciones Integradas.
# Cada entrada debe declarar una GlobalIndicatorDefinition con sus kpi_key explícitas y uno o
# ambos scopes de presentación. Permanece vacío mientras no exista un inventario canónico actual.
INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS: tuple[DashboardGlobalIndicatorBinding, ...] = ()
