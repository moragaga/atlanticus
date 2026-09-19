# La API Web queda separada del __init__ raíz para mantener Dash como dependencia opcional.
from atlanticus.web.profiles.configuration.web.layout import (
    build_profiles_admin_configuration,
    configured_profiles_page,
)
from atlanticus.web.profiles.configuration.web.models import (
    LocalIdentityBadge,
    LocalIdentityBadgeProvider,
    ProfilesAdminWebContext,
)
from atlanticus.web.profiles.configuration.web.module import create_profiles_admin_web_module

__all__ = [
    'LocalIdentityBadge',
    'LocalIdentityBadgeProvider',
    'ProfilesAdminWebContext',
    'build_profiles_admin_configuration',
    'configured_profiles_page',
    'create_profiles_admin_web_module',
]
