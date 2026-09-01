from dash import html, register_page

register_page(__name__, path_template='/<module>', name='Manager module')


def layout(module: str | None = None, **_kwargs):
    del module
    return html.Div()
