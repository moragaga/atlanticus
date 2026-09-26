from __future__ import annotations

from dataclasses import replace

from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_local_operational_composition,
)
from ada.web.operational_render_binding import OperationalRenderBinding

from application.modules.example.module import create_example_module


def create_composition(_binding: OperationalRenderBinding | None) -> AdaApplicationComposition:
    generic = create_local_operational_composition()
    return replace(generic, modules=(*generic.modules, create_example_module()))
