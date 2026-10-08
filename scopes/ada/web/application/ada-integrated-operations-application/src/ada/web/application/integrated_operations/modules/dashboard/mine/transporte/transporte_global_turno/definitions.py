from ada.web.ui.inline_row import InlineComparisonRowDefinition

TRANSPORTE_GLOBAL_TURNO_KPI_KEY = 'transporte_global_turno'

TRANSPORTE_GLOBAL_TURNO_ROW_DEFINITIONS = {
    'rendimiento': InlineComparisonRowDefinition(label='Rendimiento', unit='t/h'),
    'uebd': InlineComparisonRowDefinition(label='UEBD', unit='%'),
    'ciclo': InlineComparisonRowDefinition(label='Ciclo', unit='min'),
    'velocidad_media': InlineComparisonRowDefinition(label='Velocidad Media', unit='km/h'),
    'distancia_media': InlineComparisonRowDefinition(label='Distancia Media', unit='km'),
}

TRANSPORTE_GLOBAL_TURNO_ROW_KEYS = tuple(TRANSPORTE_GLOBAL_TURNO_ROW_DEFINITIONS)
