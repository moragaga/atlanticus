from dash import html, register_page

register_page(__name__, path='/', name='Inicio', order=0)

layout = html.Section(
    [
        html.H1('ADA Command Center'),
        html.P('Aplicación base integrada de ADA Command Center.'),
        html.P('La configuración administrativa está disponible desde Manager.'),
    ],
    id='ada-command-center-home',
)
