import pytest

pytest.importorskip('dash')

from atlanticus.web.compositions.navigation_manager import (
    NAVIGATION_MANAGER_PROJECTION_SERVICE,
    NAVIGATION_MANAGER_SOURCE_SERVICE,
    NAVIGATION_MANAGER_VALIDATION_SERVICE,
    compose_navigation_manager,
)
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
    NavigationProfileOption,
)
from atlanticus.web.navigation.projection.local import (
    LocalNavigationProjectionStore,
    LocalNavigationProjectionStoreSettings,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='tester',
        display_name='Tester',
        access_keys=('navigation.manage',),
        is_local=True,
    )


def test_navigation_manager_registers_one_generic_source_route(tmp_path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalNavigationProjectionStore(
        LocalNavigationProjectionStoreSettings(root=tmp_path / 'projection')
    )

    composition = compose_navigation_manager(
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
        access_key='navigation.manage',
    )

    module = composition.module
    assert module.source_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.source_reader_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.source_history_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.projection_service == NAVIGATION_MANAGER_PROJECTION_SERVICE
    assert module.draft_validation_service == NAVIGATION_MANAGER_VALIDATION_SERVICE
    assert module.access_key == 'navigation.manage'
    services = ServiceRegistry()
    module.web_module.register_services(services)
    assert services.require(NAVIGATION_MANAGER_SOURCE_SERVICE) is composition.source_workflow
    assert services.require(NAVIGATION_MANAGER_PROJECTION_SERVICE) is composition.projection_service
    assert (
        services.require(NAVIGATION_MANAGER_VALIDATION_SERVICE) is composition.validation_workflow
    )


def test_navigation_manager_uses_profile_options_for_draft_validation(tmp_path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalNavigationProjectionStore(
        LocalNavigationProjectionStoreSettings(root=tmp_path / 'projection')
    )
    options = (NavigationProfileOption('guest', 'Guest'),)
    composition = compose_navigation_manager(
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
        access_key='navigation.manage',
        profile_options_provider=lambda: options,
    )
    payload = NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Home',
                href='/',
                access_mode='restricted',
                allowed_profiles=('operator',),
            ),
        )
    ).to_document()

    result = composition.validation_workflow.validate_draft(payload)

    assert not result.valid
    assert result.issues[0].code == 'navigation.profile.unknown'

class _Authorization:
    def __init__(self) -> None:
        self.calls: list[tuple[ManagerPrincipal, object]] = []

    def can_view(self, principal: ManagerPrincipal, item: object) -> bool:
        self.calls.append((principal, item))
        return True


def test_navigation_manager_exposes_product_specific_contract_without_eager_services(
    tmp_path,
) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalNavigationProjectionStore(
        LocalNavigationProjectionStoreSettings(root=tmp_path / 'projection')
    )
    authorization = _Authorization()

    composition = compose_navigation_manager(
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
        title='Navegación',
        description='Rutas y perfiles habilitados.',
        source_key=SourceKey('navigation'),
        source_name='ADA Navigation Source',
        projection_name='ADA Navigation Projection',
        access_key='navigation.manage',
        authorization=authorization,
    )

    module = composition.module
    assert module.title == 'Navegación'
    assert module.description == 'Rutas y perfiles habilitados.'
    assert module.source_key == SourceKey('navigation')
    assert module.source_name == 'ADA Navigation Source'
    assert module.projection_name == 'ADA Navigation Projection'

    class FakeApp:
        def __init__(self) -> None:
            self.registered: dict[str, object] = {}

        def callback(self, *_args, **_kwargs):
            def register(callback):
                self.registered[callback.__name__] = callback
                return callback

            return register

    app = FakeApp()
    module.web_module.register_callbacks(app, ServiceRegistry())

    app.registered['save_group'](
        1,
        None,
        'Operación',
        None,
        True,
        {'links': [], 'groups': []},
    )

    assert authorization.calls
    assert authorization.calls[-1][0] == _principal()
    assert authorization.calls[-1][1] is module
