# Expone el renderer de historial de Users para el contrato modular de Manager.
# La composición registra la capacidad sin trasladar semántica de usuarios al núcleo del Manager.

from atlanticus.web.users.configuration.web.layout import build_users_admin_configuration
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.configuration.web.module import create_users_admin_web_module
from atlanticus.web.users.configuration.web.preview import build_users_history_preview

__all__ = [
    'build_users_history_preview',
    'UsersAdminWebContext',
    'build_users_admin_configuration',
    'create_users_admin_web_module',
]
