from ada.web.ui.inline_row import InlineValueRowDefinition

NUMERO_OPERATIVO_TURNO_KPI_KEY = 'numero_operativo_turno'

NUMERO_OPERATIVO_TURNO_DEFINITIONS = {
    'efectivos': InlineValueRowDefinition(label='Efectivos'),
    'mantencion': InlineValueRowDefinition(label='Mantención'),
    'demora': InlineValueRowDefinition(label='Demora'),
    'reserva': InlineValueRowDefinition(label='Reserva'),
}

NUMERO_OPERATIVO_TURNO_KEYS = tuple(NUMERO_OPERATIVO_TURNO_DEFINITIONS)
