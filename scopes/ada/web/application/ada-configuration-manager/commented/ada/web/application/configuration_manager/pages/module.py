from dash import html, register_page

# Registra la ruta dinámica utilizada para acceder a cada módulo del ADA Manager.
# El segmento <module> identifica la ruta solicitada, mientras que la composición
# efectiva del módulo sigue siendo responsabilidad del Manager.
register_page(
    __name__,
    path_template='/manager/<module>',
    name='ADA Manager module',
)


def layout(module: str | None = None, **_kwargs):
    # Dash entrega el segmento dinámico de la URL al layout. Esta página no
    # necesita resolverlo directamente porque el framework administra la
    # superficie correspondiente.
    del module
    return html.Div()
