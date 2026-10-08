# Remanentes y Stock 3080 son KPI independientes que comparten una tarjeta.
# La definición pública de fila pertenece a la capacidad ADA UI, no al framework Web.
from ada.web.ui.inline_row import InlineValueRowDefinition

REMANENTES_SUMMARY_KPI_KEY = 'remanentes_summary_inst'
STOCK_3080_KPI_KEY = 'stock_3080_inst'
REMANENTES_UNIT = 'kt'

STOCK_3080_ROW_DEFINITION = InlineValueRowDefinition(
    label='Stock 3080',
    unit='kt',
)
