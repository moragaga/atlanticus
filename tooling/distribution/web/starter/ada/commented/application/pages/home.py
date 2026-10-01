from dash import html, register_page

# Esta ruta reemplaza el Home genérico dentro del shell de ADA. El header y Navigation siguen
# siendo provistos por ADA Generic, por lo que aquí sólo se implementa el contenido del producto.
register_page(__name__, path='/', name='Inicio', order=0)

layout = html.Section(
    [
        html.H1('Inicio'),
        html.P('Completa esta página con el contenido específico de la herramienta.'),
    ],
    id='application-home',
)
