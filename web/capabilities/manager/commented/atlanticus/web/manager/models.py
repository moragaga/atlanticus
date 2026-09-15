# Espejo pedagógico del archivo productivo equivalente.
# Define la composición declarativa de módulos Manager. Cada módulo nombra sus servicios Source, Projection y validación de forma explícita.
# Los comentarios no alteran la estructura ejecutable ni el comportamiento del archivo productivo.

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey

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
    source_key: SourceKey
    source_service: str
    source_reader_service: str
    projection_service: str
    draft_validation_service: str
    source_history_service: str | None = None
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
    history_preview_renderer: ManagerHistoryPreviewRenderer | None = None

    def __post_init__(self) -> None:
        service_keys = (
            self.source_service,
            self.source_reader_service,
            self.projection_service,
            self.draft_validation_service,
        )
        if any(not value.strip() for value in service_keys):
            raise ManagerDefinitionError('Manager module service keys must not be empty')
        if self.source_history_service is not None and not self.source_history_service.strip():
            raise ManagerDefinitionError('Manager source history service key must not be empty')


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
