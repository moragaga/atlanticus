# API pública Web de Users Configuration.
# El layout y callbacks activos son canónicos; el history preview legacy se conserva
# mientras Manager productive exact-source permanece en un incremento posterior.

from atlanticus.web.users.configuration.web.canonical_layout import (
    build_users_admin_configuration,
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.configuration.web.module import create_users_admin_web_module
from atlanticus.web.users.configuration.web.preview import build_users_history_preview

__all__ = [
    'build_users_history_preview',
    'UsersAdminWebContext',
    'build_users_admin_configuration',
    'create_users_admin_web_module',
]
