# Expone el renderer de historial de Navigation para que la composición lo registre en Manager.
# El renderer permanece dentro del módulo que conoce su contrato de rutas y permisos.

from atlanticus.web.navigation.configuration.web.layout import build_navigation_admin_configuration
from atlanticus.web.navigation.configuration.web.models import (
    NavigationAdminWebContext,
    NavigationProfileOptionsProvider,
)
from atlanticus.web.navigation.configuration.web.module import create_navigation_admin_web_module
from atlanticus.web.navigation.configuration.web.preview import build_navigation_history_preview

__all__ = [
    'build_navigation_history_preview',
    'NavigationAdminWebContext',
    'NavigationProfileOptionsProvider',
    'build_navigation_admin_configuration',
    'create_navigation_admin_web_module',
]
