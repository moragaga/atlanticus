from dash import html, register_page

register_page(__name__, path='/', name='Home', order=0)

layout = html.Main(
    [html.H1('Application Starter'), html.P('Application composition is ready.')],
    id='application-home',
)
