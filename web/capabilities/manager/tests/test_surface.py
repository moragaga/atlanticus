from atlanticus.web.manager import ManagerModule, ManagerModuleGroup, ManagerPrincipal, ManagerSurfaceDefinition
from atlanticus.web.source.models import SourceKey


def test_surface_definition_keeps_domain_services_in_module_composition() -> None:
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

    assert definition.modules == (module,)
    assert definition.modules[0].source_key == SourceKey('tools')
