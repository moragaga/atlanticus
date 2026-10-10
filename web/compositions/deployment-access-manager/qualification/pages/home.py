from dash import html, register_page

register_page(__name__, path='/', name='Qualification')
layout = html.Div('Operational qualification route')
