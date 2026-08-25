from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlanticus.web.assets import AssetLayer, AssetPublication
from atlanticus.web.environment import WebEnvironment
from atlanticus.web.health import HealthRegistry
from atlanticus.web.index import IndexPageDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

if TYPE_CHECKING:
    from dash import Dash
    from flask import Flask

    from atlanticus.web.observability import WebObservability

LayoutFactory = Callable[[ServiceRegistry], Any]


@dataclass(frozen=True, slots=True)
class ApplicationMetadata:
    application_id: str
    display_name: str
    version: str


@dataclass(frozen=True, slots=True)
class DashSettings:
    external_stylesheets: tuple[str, ...] = ()
    external_scripts: tuple[str, ...] = ()
    include_assets_files: bool = True
    suppress_callback_exceptions: bool = True
    prevent_initial_callbacks: bool = False
    update_title: str | None = None
    meta_tags: tuple[Mapping[str, str], ...] = (
        {'name': 'viewport', 'content': 'width=device-width, initial-scale=1'},
    )


@dataclass(frozen=True, slots=True)
class WebApplicationDefinition:
    import_name: str
    metadata: ApplicationMetadata
    publications_root: Path
    layout: LayoutFactory
    modules: tuple[WebModule, ...] = ()
    page_packages: tuple[str, ...] = ()
    asset_layers: tuple[AssetLayer, ...] = ()
    index: IndexPageDefinition = field(default_factory=IndexPageDefinition)
    dash: DashSettings = field(default_factory=DashSettings)
    flask_config: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WebApplicationRuntime:
    server: Flask
    dash: Dash
    services: ServiceRegistry
    health: HealthRegistry
    environment: WebEnvironment
    assets: AssetPublication
    observability: WebObservability
    page_modules: tuple[str, ...]
