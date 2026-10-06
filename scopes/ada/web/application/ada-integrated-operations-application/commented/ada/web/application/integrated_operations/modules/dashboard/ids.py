# IDs del contenedor principal ya existentes antes de este incremento.
DASHBOARD_ROOT_ID = 'ada-integrated-operations-dashboard'
DASHBOARD_SCOPES_ID = 'ada-integrated-operations-dashboard-scopes'


def dashboard_component_id(component_key: str) -> str:
    # La identidad Dash se deriva de la clave visual; no depende de la clave del Tool.
    return f'ada-integrated-operations-component-{component_key}'


def dashboard_card_id(card_key: str) -> str:
    # Cada card tiene un wrapper estable para futuras interacciones y pruebas funcionales.
    return f'ada-integrated-operations-card-{card_key}'


def dashboard_card_content_id(card_key: str) -> str:
    # El contenido queda direccionable sin obligar al callback futuro a reemplazar toda la card.
    return f'ada-integrated-operations-card-{card_key}-content'
