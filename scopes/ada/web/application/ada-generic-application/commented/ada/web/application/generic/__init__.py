# Espejo comentado: API pública de la composición ADA y sus fronteras de render operacional.
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_ada_alarm_surface_modules,
    create_ada_branding_modules,
    create_ada_operational_shell_modules,
    create_ada_runtime_experience_modules,
    create_ada_shared_ui_modules,
    create_local_identity_modules,
    create_local_operational_composition,
    create_operational_navigation_modules,
)
from ada.web.application.generic.layout import (
    build_body_application_layout,
    create_ada_operational_layout,
)
from ada.web.application.generic.operational_latest import (
    OPERATIONAL_LATEST_HOST_TYPE,
    AdaOperationalKpiValueFactory,
    AdaOperationalLatestRenderer,
    OperationalLatestPresentation,
    build_operational_latest_body,
    build_operational_latest_kpi,
    create_operational_latest_render_module,
    materialize_operational_latest_hosts,
    operational_latest_host_id,
    resolve_operational_latest_display_value,
)
from ada.web.application.generic.operational_render import (
    AdaOperationalBodyFactory,
    AdaOperationalComponentRenderer,
    materialize_operational_components,
)
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.ui.content_state import ContentStatePresentationMode

__all__ = [
    'OPERATIONAL_LATEST_HOST_TYPE',
    'AdaApplicationComposition',
    'AdaOperationalBodyFactory',
    'AdaOperationalComponentRenderer',
    'AdaOperationalKpiValueFactory',
    'AdaOperationalLatestRenderer',
    'ContentStatePresentationMode',
    'OperationalLatestPresentation',
    'build_body_application_layout',
    'build_operational_latest_body',
    'build_operational_latest_kpi',
    'create_ada_alarm_surface_modules',
    'create_ada_branding_modules',
    'create_ada_operational_layout',
    'create_ada_operational_shell_modules',
    'create_ada_runtime_experience_modules',
    'create_ada_shared_ui_modules',
    'create_application_definition',
    'create_application_runtime',
    'create_local_identity_modules',
    'create_local_operational_composition',
    'create_operational_latest_render_module',
    'create_operational_navigation_modules',
    'materialize_operational_components',
    'materialize_operational_latest_hosts',
    'operational_latest_host_id',
    'resolve_operational_latest_display_value',
]
