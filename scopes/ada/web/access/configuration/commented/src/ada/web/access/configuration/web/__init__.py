# Superficie Web administrativa de ADA Access.
# La presentación vive en la capability; el wiring de Manager permanece en la aplicación ADA.

from ada.web.access.configuration.web.layout import build_ada_access_admin_configuration
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext
from ada.web.access.configuration.web.module import create_ada_access_admin_web_module

__all__ = [
    'AdaAccessAdminWebContext',
    'build_ada_access_admin_configuration',
    'create_ada_access_admin_web_module',
]
