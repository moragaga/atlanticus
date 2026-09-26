from dash import html, register_page

register_page(__name__, path='/example', name='Example')

layout = html.Section(
    [
        html.H2('Example module'),
        html.Button('Activate', id='starter-example-button'),
        html.Div(id='starter-example-result'),
    ],
    id='starter-example-page',
)
