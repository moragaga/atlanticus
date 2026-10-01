from dash import html, register_page

register_page(__name__, path='/', name='Inicio', order=0)

layout = html.Section(
    [
        html.H1('Inicio'),
        html.P('Completa esta página con el contenido específico de la herramienta.'),
    ],
    id='application-home',
)
