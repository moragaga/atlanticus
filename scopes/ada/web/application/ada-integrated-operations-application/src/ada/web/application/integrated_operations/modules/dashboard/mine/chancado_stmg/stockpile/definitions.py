from ada.web.ui.stockpile import StockpileDefinition, StockpileVariant

STOCKPILE_MINA_SCALE_MAX_M = 28.0

STOCKPILE_MINA_KPI_KEYS = (
    ('pila_1', 'altura_pila_stockpile_mina_1_p_inst', 'altura_pila_stockpile_mina_1_m_inst'),
    ('pila_2', 'altura_pila_stockpile_mina_2_p_inst', 'altura_pila_stockpile_mina_2_m_inst'),
)

STOCKPILE_MINA_DEFINITIONS = tuple(
    StockpileDefinition(
        key=key,
        variant=StockpileVariant.VARIABLE_HEIGHT,
        scale_max_m=STOCKPILE_MINA_SCALE_MAX_M,
        max_width_px=115,
        max_height_px=90,
    )
    for key, _, _ in STOCKPILE_MINA_KPI_KEYS
)
