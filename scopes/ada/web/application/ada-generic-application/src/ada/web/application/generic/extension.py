from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ada.web.operational_render_binding import OperationalRenderBinding
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import WebModule


@dataclass(frozen=True, slots=True)
class AdaApplicationExtension:
    modules: tuple[WebModule, ...] = ()
    page_packages: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.modules, tuple):
            raise TypeError('Application extension modules must be a tuple')
        if any(not isinstance(module, WebModule) for module in self.modules):
            raise TypeError('Application extension modules must be WebModule values')
        if self.page_packages is None:
            return
        if not isinstance(self.page_packages, tuple):
            raise TypeError('Application extension page packages must be a tuple or None')
        normalized: list[str] = []
        for package in self.page_packages:
            if not isinstance(package, str) or not package or package != package.strip():
                raise ValueError(
                    'Application extension page package must be a non-empty trimmed string'
                )
            normalized.append(package)
        if len(set(normalized)) != len(normalized):
            raise ValueError('Application extension page packages must not contain duplicates')


AdaApplicationExtensionFactory = Callable[
    [OperationalRenderBinding | None], AdaApplicationExtension
]


def extend_ada_application_definition(
    definition: WebApplicationDefinition,
    extension: AdaApplicationExtension,
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('Application extension requires WebApplicationDefinition')
    if not isinstance(extension, AdaApplicationExtension):
        raise TypeError('extension must be AdaApplicationExtension')
    return replace(
        definition,
        modules=(*definition.modules, *extension.modules),
        page_packages=(
            definition.page_packages
            if extension.page_packages is None
            else extension.page_packages
        ),
    )
