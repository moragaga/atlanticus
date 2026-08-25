from dash import html, register_page

register_page(__name__, path='/', name='Inicio', order=0)

layout = html.Section(
    [
        html.H1('ADA'),
        html.P('Aplicación genérica de operaciones.'),
        html.P('Las capacidades ADA se integrarán progresivamente sobre esta superficie.'),
    ],
    id='ada-generic-home',
)
