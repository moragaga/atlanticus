# Página mínima que registra /manager; la superficie Manager renderiza el contenido real.
from dash import html, register_page

register_page(__name__, path='/manager', name='ADA Command Center Manager')

layout = html.Div()
