from dash import html, register_page

register_page(__name__, path='/manager', name='Manager')
layout = html.Div('Manager route placeholder')
