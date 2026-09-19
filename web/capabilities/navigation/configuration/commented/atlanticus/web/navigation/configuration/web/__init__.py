# Superficie pública alineada con el contrato vigente, sin exports legacy.
from atlanticus.web.navigation.configuration.web.layout import build_navigation_admin_configuration
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext
from atlanticus.web.navigation.configuration.web.module import create_navigation_admin_web_module
from atlanticus.web.navigation.configuration.web.preview import build_navigation_history_preview

__all__ = [
    'build_navigation_history_preview',
    'NavigationAdminWebContext',
    'build_navigation_admin_configuration',
    'create_navigation_admin_web_module',
]
