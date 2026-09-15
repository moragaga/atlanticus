from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.callbacks import register_manager_callbacks
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey


class RecorderApp:
    def __init__(self) -> None:
        self.callbacks = []

    def callback(self, *dependencies, **options):
        def register(function):
            self.callbacks.append((dependencies, options, function))
            return function
        return register


def test_manager_callbacks_register_for_generic_module_without_resolving_services_eagerly() -> None:
    principal = ManagerPrincipal('local', 'Local', is_local=True)
    module = ManagerModule(
        key='tools', group_key='configuration', title='Tools', route='/tools', order=10,
        layout=lambda _services: None, source_key=SourceKey('tools'),
        source_service='tools.source', source_reader_service='tools.reader',
        source_history_service='tools.history', projection_service='tools.projection',
        draft_validation_service='tools.validation',
    )
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    app = RecorderApp()

    register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=ServiceRegistry(),
        authorization=DefaultManagerAuthorizationPolicy(),
    )

    assert app.callbacks
