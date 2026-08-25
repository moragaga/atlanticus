from __future__ import annotations

# Compone Flask, módulos, assets y Dash Pages en un orden determinista.

import importlib.util
import re
from pathlib import Path

from dash import Dash
from flask import Flask, request

from atlanticus.web.assets import AssetLayer, publish_asset_layers
from atlanticus.web.environment import WebEnvironment, resolve_environment
from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.health import HealthRegistry, register_health_routes
from atlanticus.web.index import render_index_string
from atlanticus.web.models import WebApplicationDefinition, WebApplicationRuntime
from atlanticus.web.observability import WebObservability, configure_web_observability
from atlanticus.web.pages import import_page_packages, validate_page_packages
from atlanticus.web.services import ServiceRegistry

_APPLICATION_ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_EXTENSION_KEY = 'atlanticus_web'
_DASH_SETUP_DEFERRED_PATH_PREFIXES = ('/assets/', '/health/', '/.auth/')


# Las rutas públicas de infraestructura no deben disparar la validación inicial de una UI
# que puede depender de identidad request-scoped. Dash se inicializa en el primer request UI real.
class _AtlanticusDash(Dash):
    def _setup_server(self):
        if request.path.startswith(_DASH_SETUP_DEFERRED_PATH_PREFIXES):
            return None
        return super()._setup_server()


BASE_ASSET_LAYER = AssetLayer(
    name='atlanticus_web',
    load_order=10,
    package='atlanticus.web',
    resource_directory='resources/base',
)


def create_web_application(definition: WebApplicationDefinition) -> WebApplicationRuntime:
    _validate_definition(definition)
    environment = resolve_environment()
    observability = configure_web_observability(
        application=definition.metadata.application_id,
        json_output=environment.is_production,
    )

    try:
        return _compose_web_application(
            definition=definition,
            environment=environment,
            observability=observability,
        )
    except Exception as error:
        observability.critical(
            'web.startup.failed',
            'Web application startup failed',
            exception=error,
        )
        raise


def run_web_application(
    runtime: WebApplicationRuntime,
    *,
    host: str = '0.0.0.0',
    port: int = 8050,
) -> None:
    runtime.server.run(
        host=host,
        port=port,
        debug=runtime.environment.is_local,
        use_reloader=runtime.environment.is_local,
    )


def _compose_web_application(
    *,
    definition: WebApplicationDefinition,
    environment: WebEnvironment,
    observability: WebObservability,
) -> WebApplicationRuntime:
    services = ServiceRegistry()
    health = HealthRegistry()

    for module in definition.modules:
        if module.register_services is not None:
            module.register_services(services)
    services.freeze()

    # Local conserva assets legibles; producción publica el snapshot CSS/JS optimizado.
    assets = publish_asset_layers(
        layers=_collect_asset_layers(definition),
        publications_root=definition.publications_root,
        optimize=environment.is_production,
    )

    # Flask no puede inferir de forma segura el instance path cuando la raíz usa
    # un namespace package.
    flask_paths = _resolve_namespace_flask_paths(definition.import_name)
    if flask_paths is None:
        server = Flask(definition.import_name)
    else:
        root_path, instance_path = flask_paths
        server = Flask(
            definition.import_name,
            root_path=str(root_path),
            instance_path=str(instance_path),
        )
    server.config.update(dict(definition.flask_config))
    observability.attach_flask(server)

    for module in definition.modules:
        if module.register_middlewares is not None:
            module.register_middlewares(server, services)

    for module in definition.modules:
        if module.register_health_checks is not None:
            module.register_health_checks(health, services)

    register_health_routes(
        server,
        application_id=definition.metadata.application_id,
        version=definition.metadata.version,
        environment=environment.value,
        registry=health,
    )

    for module in definition.modules:
        if module.register_routes is not None:
            module.register_routes(server, services)

    index_string = render_index_string(
        application_id=definition.metadata.application_id,
        display_name=definition.metadata.display_name,
        version=definition.metadata.version,
        definition=definition.index,
        module_contributions=((module.name, module.index) for module in definition.modules),
    )

    dash_settings = definition.dash
    dash_app = _AtlanticusDash(
        definition.import_name,
        server=server,
        routes_pathname_prefix='/',
        requests_pathname_prefix='/',
        use_pages=True,
        pages_folder='',
        title=definition.metadata.display_name,
        assets_folder=str(assets.assets_root),
        external_stylesheets=list(dash_settings.external_stylesheets),
        external_scripts=list(dash_settings.external_scripts),
        include_assets_files=dash_settings.include_assets_files,
        suppress_callback_exceptions=dash_settings.suppress_callback_exceptions,
        prevent_initial_callbacks=dash_settings.prevent_initial_callbacks,
        update_title=dash_settings.update_title,
        meta_tags=[dict(item) for item in dash_settings.meta_tags],
    )
    dash_app.index_string = index_string

    page_modules = import_page_packages(_collect_page_packages(definition))
    dash_app.layout = lambda: definition.layout(services)

    for module in definition.modules:
        if module.register_callbacks is not None:
            module.register_callbacks(dash_app, services)

    runtime = WebApplicationRuntime(
        server=server,
        dash=dash_app,
        services=services,
        health=health,
        environment=environment,
        assets=assets,
        observability=observability,
        page_modules=page_modules,
    )
    if _EXTENSION_KEY in server.extensions:
        raise WebDefinitionError('Atlanticus Web is already registered in this Flask application')
    server.extensions[_EXTENSION_KEY] = runtime
    return runtime


def _resolve_namespace_flask_paths(import_name: str) -> tuple[Path, Path] | None:
    # Solo intervenimos cuando el primer segmento del import pertenece a un namespace package.
    # Las aplicaciones normales conservan exactamente la resolución nativa de Flask.
    root_name = import_name.partition('.')[0]
    try:
        root_spec = importlib.util.find_spec(root_name)
    except (ImportError, ValueError):
        return None

    if (
        root_spec is None
        or not root_spec.submodule_search_locations
        or root_spec.origin not in {None, 'namespace'}
    ):
        return None

    # La aplicación concreta debe poder resolverse a una ubicación física única.
    try:
        package_spec = importlib.util.find_spec(import_name)
    except (ImportError, ValueError) as error:
        raise WebDefinitionError(
            f'Application import name could not be resolved: {import_name}'
        ) from error

    if package_spec is None:
        raise WebDefinitionError(
            f'Application import name could not be resolved: {import_name}'
        )

    if package_spec.origin not in {None, 'namespace'}:
        root_path = Path(package_spec.origin).resolve().parent
    else:
        locations = tuple(package_spec.submodule_search_locations or ())
        if len(locations) != 1:
            raise WebDefinitionError(
                f'Application import name must resolve to one filesystem location: {import_name}'
            )
        root_path = Path(locations[0]).resolve()

    # Flask solo necesita un path absoluto; se usa el directorio hermano "instance" para mantener
    # la semántica habitual de una carpeta de instancia junto al paquete de aplicación.
    return root_path, root_path.parent / 'instance'


def _collect_asset_layers(definition: WebApplicationDefinition) -> tuple[AssetLayer, ...]:
    module_layers = tuple(layer for module in definition.modules for layer in module.asset_layers)
    return (BASE_ASSET_LAYER, *definition.asset_layers, *module_layers)


def _collect_page_packages(definition: WebApplicationDefinition) -> tuple[str, ...]:
    packages = (
        *definition.page_packages,
        *(package for module in definition.modules for package in module.page_packages),
    )
    if not packages:
        raise WebDefinitionError('Application must define at least one page package')
    validate_page_packages(packages)
    return packages


def _validate_definition(definition: WebApplicationDefinition) -> None:
    metadata = definition.metadata
    if not definition.import_name.strip():
        raise WebDefinitionError('Application import name must not be empty')
    if not _APPLICATION_ID_PATTERN.fullmatch(metadata.application_id):
        raise WebDefinitionError('Application id has an invalid format')
    if not metadata.display_name.strip():
        raise WebDefinitionError('Application display name must not be empty')
    if not metadata.version.strip():
        raise WebDefinitionError('Application version must not be empty')
    if not callable(definition.layout):
        raise WebDefinitionError('Application layout must be callable')

    module_names: set[str] = set()
    for module in definition.modules:
        normalized = module.name.strip()
        if not _APPLICATION_ID_PATTERN.fullmatch(normalized) or normalized != module.name:
            raise WebDefinitionError('Module name has an invalid format')
        if normalized in module_names:
            raise WebDefinitionError(f'Module already registered: {normalized}')
        module_names.add(normalized)
