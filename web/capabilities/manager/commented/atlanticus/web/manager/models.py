# Declara el renderer opcional que cada módulo puede aportar para interpretar una revisión histórica.
# La responsabilidad semántica permanece en el módulo mientras Manager conserva la orquestación genérica.

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

ManagerLayoutFactory = Callable[[ServiceRegistry], object]
ManagerHistoryPreviewRenderer = Callable[[dict[str, object]], object]
ManagerPrincipalProvider = Callable[[], 'ManagerPrincipal']

_PROFILE_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_ROUTE_PREFIX_PATTERN = re.compile(r'^/[a-z0-9][a-z0-9/_-]*$')
@dataclass(frozen=True, slots=True)
class ManagerPrincipal:
    subject_id: str
    display_name: str
    profile_keys: tuple[str, ...] = ()
    access_keys: tuple[str, ...] = ()
    is_local: bool = False

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ManagerDefinitionError('Manager principal subject id must not be empty')
        if not self.display_name.strip():
            raise ManagerDefinitionError('Manager principal display name must not be empty')
        for key in self.profile_keys + self.access_keys:
            if not _PROFILE_KEY_PATTERN.fullmatch(key):
                raise ManagerDefinitionError('Manager principal key has an invalid format')


@dataclass(frozen=True, slots=True)
class ManagerModuleAccess:
    view: str | None = None
    validate: str | None = None
    project: str | None = None
    publish: str | None = None


@dataclass(frozen=True, slots=True)
class ManagerModuleGroup:
    key: str
    title: str
    order: int


@dataclass(frozen=True, slots=True)
class ManagerModule:
    key: str
    group_key: str
    title: str
    route: str
    order: int
    layout: ManagerLayoutFactory
    workflow_service: str
    description: str = ''
    access: ManagerModuleAccess = field(default_factory=ManagerModuleAccess)
    web_module: WebModule | None = None
    source_signal_id: str | None = None
    preamble: ManagerLayoutFactory | None = None
    workflow_section_title: str = 'Estado y trazabilidad'
    content_section_title: str = 'Configuración'
    default_section: str = 'content'
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    force_publish_enabled: bool = False
    history_preview_renderer: ManagerHistoryPreviewRenderer | None = None


@dataclass(frozen=True, slots=True)
class ManagerSurfaceDefinition:
    principal_provider: ManagerPrincipalProvider
    groups: tuple[ManagerModuleGroup, ...]
    modules: tuple[ManagerModule, ...]
    route_prefix: str = ''
    web_modules: tuple[WebModule, ...] = ()

    def __post_init__(self) -> None:
        prefix = self.route_prefix
        if prefix and (not _ROUTE_PREFIX_PATTERN.fullmatch(prefix) or prefix.endswith('/')):
            raise ManagerDefinitionError('Manager route prefix has an invalid format')
