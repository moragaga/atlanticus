from __future__ import annotations

from dash.development.base_component import Component

from .desaladora import DesaladoraReading, build_desaladora
from .puerto import PuertoReading, build_puerto


def build_puerto_component(
    puerto: PuertoReading, desaladora: DesaladoraReading
) -> tuple[Component, Component]:
    return build_puerto(puerto), build_desaladora(desaladora)
