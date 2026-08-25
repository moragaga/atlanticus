from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from atlanticus.web.assets import AssetLayer
from atlanticus.web.health import HealthRegistry
from atlanticus.web.index import IndexContribution
from atlanticus.web.services import ServiceRegistry

if TYPE_CHECKING:
    from dash import Dash
    from flask import Flask

ServiceRegistrar = Callable[[ServiceRegistry], None]
HealthRegistrar = Callable[[HealthRegistry, ServiceRegistry], None]
FlaskRegistrar = Callable[['Flask', ServiceRegistry], None]
CallbackRegistrar = Callable[['Dash', ServiceRegistry], None]


@dataclass(frozen=True, slots=True)
class WebModule:
    name: str
    page_packages: tuple[str, ...] = ()
    asset_layers: tuple[AssetLayer, ...] = ()
    register_services: ServiceRegistrar | None = None
    register_health_checks: HealthRegistrar | None = None
    register_middlewares: FlaskRegistrar | None = None
    register_routes: FlaskRegistrar | None = None
    register_callbacks: CallbackRegistrar | None = None
    index: IndexContribution = field(default_factory=IndexContribution)
