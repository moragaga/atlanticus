import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.models import (
    ApplicationMetadata,
    DashSettings,
    IndexPageDefinition,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

ManagerLayoutFactory = Callable[[ServiceRegistry], object]
ManagerHistoryPreviewRenderer = Callable[[dict[str, object]], object]
ManagerPrincipalProvider = Callable[[], 'ManagerPrincipal']

_PROFILE_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_ROUTE_PREFIX_PATTERN = re.compile(r'^/[a-z0-9][a-z0-9/_-]*$')
_BRAND_MARK_ROLES = frozenset({'product', 'framework', 'organization'})


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
class ManagerBrandMark:
    role: str
    logo_src: str
    logo_alt: str
    label: str | None = None
    eyebrow: str | None = None

    def __post_init__(self) -> None:
        if self.role not in _BRAND_MARK_ROLES:
            raise ManagerDefinitionError('Manager brand role is not supported')
        if not self.logo_src.strip():
            raise ManagerDefinitionError('Manager brand logo source must not be empty')
        if not self.logo_alt.strip():
            raise ManagerDefinitionError('Manager brand logo alternative text must not be empty')
        if self.label is not None and not self.label.strip():
            raise ManagerDefinitionError('Manager brand label must not be empty')
        if self.eyebrow is not None and not self.eyebrow.strip():
            raise ManagerDefinitionError('Manager brand eyebrow must not be empty')


@dataclass(frozen=True, slots=True)
class ManagerBrand:
    marks: tuple[ManagerBrandMark, ...]

    def __post_init__(self) -> None:
        if not self.marks:
            raise ManagerDefinitionError('Manager brand must contain at least one mark')
        roles = tuple(mark.role for mark in self.marks)
        if len(set(roles)) != len(roles):
            raise ManagerDefinitionError('Manager brand roles must be unique')
        if 'product' not in roles:
            raise ManagerDefinitionError('Manager brand must contain a product mark')


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
    default_module_key: str
    route_prefix: str = ''
    web_modules: tuple[WebModule, ...] = ()

    def __post_init__(self) -> None:
        prefix = self.route_prefix
        if prefix and (not _ROUTE_PREFIX_PATTERN.fullmatch(prefix) or prefix.endswith('/')):
            raise ManagerDefinitionError('Manager route prefix has an invalid format')
        if not self.default_module_key.strip():
            raise ManagerDefinitionError('Manager default module key must not be empty')


@dataclass(frozen=True, slots=True)
class ManagerApplicationDefinition:
    import_name: str
    metadata: ApplicationMetadata
    publications_root: Path
    surface: ManagerSurfaceDefinition
    subtitle: str = 'Gestión de configuraciones y proyecciones'
    brand: ManagerBrand | None = None
    web_modules: tuple[WebModule, ...] = ()
    index: IndexPageDefinition = field(default_factory=IndexPageDefinition)
    dash: DashSettings = field(default_factory=DashSettings)
    flask_config: Mapping[str, object] = field(default_factory=dict)
    header_actions: ManagerLayoutFactory | None = None
    shell_overlays: ManagerLayoutFactory | None = None
