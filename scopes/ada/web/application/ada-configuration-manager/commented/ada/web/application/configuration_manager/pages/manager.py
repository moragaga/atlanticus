from dash import html, register_page

# Registra la entrada raíz del ADA Manager dentro del sistema de páginas de Dash.
# La página permanece intencionalmente vacía porque la superficie real del Manager
# se compone posteriormente mediante el framework y sus módulos registrados.
register_page(__name__, path='/manager', name='ADA Manager')

# Dash exige un layout para la página registrada. Aquí funciona únicamente como
# punto de montaje; no contiene lógica ni presentación propia del Manager.
layout = html.Div()
