from __future__ import annotations

from dataclasses import replace

from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_local_operational_composition,
)
from ada.web.operational_render_binding import OperationalRenderBinding

from application.modules import create_application_modules

_APPLICATION_PAGE_PACKAGES = ("application.pages",)


def create_composition(_binding: OperationalRenderBinding | None) -> AdaApplicationComposition:
    generic = create_local_operational_composition()
    return replace(
        generic,
        modules=(*generic.modules, *create_application_modules()),
        page_packages=_APPLICATION_PAGE_PACKAGES,
    )
