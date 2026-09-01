from atlanticus.web.manager.authorization import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
)
from atlanticus.web.manager.models import ManagerSurfaceDefinition
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web import (
    build_manager_surface,
    manager_asset_layer,
    register_manager_callbacks,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry


class ManagerSurface:
    def __init__(
        self,
        definition: ManagerSurfaceDefinition,
        *,
        authorization: ManagerAuthorizationPolicy | None = None,
    ) -> None:
        self._definition = definition
        self._authorization = authorization or DefaultManagerAuthorizationPolicy()
        self._registry = ManagerModuleRegistry(
            definition.groups,
            definition.modules,
            route_prefix=definition.route_prefix,
        )
        self._registry.require(definition.default_module_key)
        self._web_modules = self._build_web_modules()

    @property
    def definition(self) -> ManagerSurfaceDefinition:
        return self._definition

    @property
    def registry(self) -> ManagerModuleRegistry:
        return self._registry

    @property
    def authorization(self) -> ManagerAuthorizationPolicy:
        return self._authorization

    @property
    def default_path(self) -> str:
        return self._registry.route_for(self._registry.require(self._definition.default_module_key))

    @property
    def web_modules(self) -> tuple[WebModule, ...]:
        return self._web_modules

    def layout(self, services: ServiceRegistry) -> object:
        return build_manager_surface(
            definition=self._definition,
            registry=self._registry,
            services=services,
            principal=self._definition.principal_provider(),
            authorization=self._authorization,
        )

    def _build_web_modules(self) -> tuple[WebModule, ...]:
        def register_callbacks(app: object, services: ServiceRegistry) -> None:
            register_manager_callbacks(
                app,
                definition=self._definition,
                registry=self._registry,
                services=services,
                authorization=self._authorization,
            )

        manager_module = WebModule(
            name='manager-surface',
            asset_layers=(manager_asset_layer(),),
            register_callbacks=register_callbacks,
        )
        module_web_modules = tuple(
            module.web_module for module in self._registry.modules if module.web_module is not None
        )
        return self._definition.web_modules + module_web_modules + (manager_module,)
