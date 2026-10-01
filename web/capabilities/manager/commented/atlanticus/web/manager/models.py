# Espejo pedagógico: mantiene el mismo AST que producción y documenta el contrato Manager en español.
import re
from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey

ManagerLayoutFactory = Callable[[ServiceRegistry], object]
ManagerHistoryPreviewRenderer = Callable[[dict[str, object]], object]
ManagerPrincipalProvider = Callable[[], 'ManagerPrincipal']

_PROFILE_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_ROUTE_PREFIX_PATTERN = re.compile(r'^/[a-z0-9][a-z0-9/_-]*$')


# El principal mantiene permisos granulares y una señal explícita de administración total.
@dataclass(frozen=True, slots=True)
class ManagerPrincipal:
    subject_id: str
    display_name: str
    profile_keys: tuple[str, ...] = ()
    access_keys: tuple[str, ...] = ()
    is_local: bool = False
    administrative_override: bool = False

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ManagerDefinitionError('Manager principal subject id must not be empty')
        if not self.display_name.strip():
            raise ManagerDefinitionError('Manager principal display name must not be empty')
        for key in self.profile_keys + self.access_keys:
            if not _PROFILE_KEY_PATTERN.fullmatch(key):
                raise ManagerDefinitionError('Manager principal key has an invalid format')


# El consumidor define marcas opcionales; ninguna marca es obligatoria para Manager.
@dataclass(frozen=True, slots=True)
class ManagerHeaderBrandMark:
    role: str
    logo_src: str
    logo_alt: str
    label: str | None = None
    eyebrow: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {'product', 'framework', 'organization'}:
            raise ManagerDefinitionError('Manager brand role is not supported')
        source = self.logo_src
        if (
            not re.fullmatch(r'/assets/[A-Za-z0-9._/-]+', source)
            or '..' in source.split('/')
            or '//' in source
        ):
            raise ManagerDefinitionError('Manager brand must reference a published local asset')
        if not self.logo_alt.strip():
            raise ManagerDefinitionError('Manager brand alternative text must not be empty')
        if self.label is not None and not self.label.strip():
            raise ManagerDefinitionError('Manager brand label must not be empty')
        if self.eyebrow is not None and not self.eyebrow.strip():
            raise ManagerDefinitionError('Manager brand eyebrow must not be empty')


@dataclass(frozen=True, slots=True)
class ManagerModuleGroup:
    key: str
    title: str
    order: int


@dataclass(frozen=True, slots=True)
class ManagerEntry:
    key: str
    group_key: str
    title: str
    route: str
    order: int
    layout: ManagerLayoutFactory
    description: str = ''
    access_key: str | None = None
    web_module: WebModule | None = None


# La vista complementaria no participa del ciclo de vida del módulo.
@dataclass(frozen=True, slots=True)
class ManagerCompanionView:
    title: str
    layout: ManagerLayoutFactory

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ManagerDefinitionError('Manager companion title must not be empty')


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
    access_key: str | None = None
    web_module: WebModule | None = None
    source_signal_id: str | None = None
    preamble: ManagerLayoutFactory | None = None
    workflow_section_title: str = 'Estado y trazabilidad'
    content_section_title: str = 'Configuración'
    default_section: str = 'content'
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    history_preview_renderer: ManagerHistoryPreviewRenderer | None = None
    companion_view: ManagerCompanionView | None = None
    primary_view_title: str | None = None
    default_primary_view: str = 'module'

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
        if self.companion_view is not None and not isinstance(self.companion_view, ManagerCompanionView):
            raise ManagerDefinitionError('Manager companion view has an invalid type')
        if self.primary_view_title is not None and not self.primary_view_title.strip():
            raise ManagerDefinitionError('Manager primary view title must not be empty')
        if self.default_primary_view not in {'module', 'companion'}:
            raise ManagerDefinitionError('Manager default primary view is invalid')
        if self.default_primary_view == 'companion' and self.companion_view is None:
            raise ManagerDefinitionError('Manager default companion view requires a companion')


@dataclass(frozen=True, slots=True)
class ManagerSurfaceDefinition:
    principal_provider: ManagerPrincipalProvider
    groups: tuple[ManagerModuleGroup, ...]
    modules: tuple[ManagerModule, ...]
    route_prefix: str = ''
    web_modules: tuple[WebModule, ...] = ()
    entries: tuple[ManagerEntry, ...] = ()
    # El retorno a una aplicación es opt-in: Manager no conoce rutas operacionales.
    application_home_href: str | None = None
    header_brand_marks: tuple[ManagerHeaderBrandMark, ...] = ()
    header_title: str = 'Manager'
    header_subtitle: str | None = None

    def __post_init__(self) -> None:
        prefix = self.route_prefix
        if prefix and (not _ROUTE_PREFIX_PATTERN.fullmatch(prefix) or prefix.endswith('/')):
            raise ManagerDefinitionError('Manager route prefix has an invalid format')
        href = self.application_home_href
        if href is not None and href != '/' and (not _ROUTE_PREFIX_PATTERN.fullmatch(href) or href.endswith('/')):
            raise ManagerDefinitionError('Manager application return route must be an internal path')
        # El header no permite dos marcas del mismo tipo ni logos no publicados.
        if not self.header_title.strip():
            raise ManagerDefinitionError('Manager header title must not be empty')
        if self.header_subtitle is not None and not self.header_subtitle.strip():
            raise ManagerDefinitionError('Manager header subtitle must not be empty')
        marks = tuple(self.header_brand_marks)
        if any(not isinstance(mark, ManagerHeaderBrandMark) for mark in marks):
            raise ManagerDefinitionError('Manager header brand marks must have valid types')
        if len({mark.role for mark in marks}) != len(marks):
            raise ManagerDefinitionError('Manager header brand roles are duplicated')
        object.__setattr__(self, 'header_brand_marks', marks)
