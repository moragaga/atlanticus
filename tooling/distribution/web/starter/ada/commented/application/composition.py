from __future__ import annotations

from dataclasses import replace

from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_local_operational_composition,
)
from ada.web.operational_render_binding import OperationalRenderBinding

from application.modules import create_application_modules

# La Tool generada es dueña de sus páginas. ADA Generic sigue siendo dueño del shell, header,
# Navigation, Manager y runtime que envuelven estas páginas.
_APPLICATION_PAGE_PACKAGES = ('application.pages',)


def create_composition(_binding: OperationalRenderBinding | None) -> AdaApplicationComposition:
    # Partimos desde la composición funcional de ADA y sólo sustituimos los puntos que el producto
    # consumidor debe poder extender: módulos adicionales y páginas de la Tool.
    generic = create_local_operational_composition()
    return replace(
        generic,
        modules=(*generic.modules, *create_application_modules()),
        page_packages=_APPLICATION_PAGE_PACKAGES,
    )
