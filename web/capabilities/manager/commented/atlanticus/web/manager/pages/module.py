# Espejo pedagógico: este archivo conserva exactamente la lógica del código productivo.
# Capability genérica del Configuration Manager de Atlanticus. Mantiene contratos y UI administrativa sin conocer dominios ni persistencias concretas.
# Los comentarios explican la intención arquitectónica; no agregan ramas, estado ni comportamiento.

from dash import html, register_page

register_page(__name__, path_template='/<module>', name='Manager module')


def layout(module: str | None = None, **_kwargs):
    del module
    return html.Div()
