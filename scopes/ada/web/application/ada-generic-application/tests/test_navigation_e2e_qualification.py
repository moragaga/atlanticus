from __future__ import annotations

import json
from dataclasses import replace

from flask import session

from ada.web.application.configuration_manager.composition import (
    NAVIGATION_DRAFT_VALIDATION_SERVICE,
    NAVIGATION_PROJECTION_SERVICE,
    NAVIGATION_SOURCE_SERVICE,
)
from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.wiring import (
    MANAGER_ACCESS_KEYS,
    NAVIGATION_SOURCE_KEY,
    compose_configuration_manager_dependencies,
)
from ada.web.application.configuration_manager.workflows import (
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
)
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.composition import (
    create_local_operational_composition,
    create_operational_navigation_modules,
)
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    create_projected_navigation_definition_provider,
)
from atlanticus.web.projection.models import ProjectionAlignment
from atlanticus.web.projection.service import SourceProjectionService

_HTML = {'Accept': 'text/html'}


def _settings(tmp_path) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_TOOL_NAMESPACE': 'navigation-qualification',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )


def _document(client, pathname: str) -> int:
    return client.get(pathname, headers=_HTML).status_code


def _draft(*, public_enabled: bool) -> dict[str, object]:
    return {
        'links': [
            {
                'key': 'home',
                'label': 'Inicio',
                'href': '/',
            },
            {
                'key': 'public',
                'label': 'Público',
                'href': '/qualification-public',
                'enabled': public_enabled,
            },
            {
                'key': 'basic',
                'label': 'Perfil básico',
                'href': '/qualification-basic',
                'allowed_profiles': ['basic'],
            },
            {
                'key': 'disabled',
                'label': 'No disponible',
                'href': '/qualification-disabled',
                'enabled': False,
            },
        ],
        'groups': [],
    }


def _publish_and_project(runtime, client, payload: dict[str, object]):
    source = runtime.services.require(
        NAVIGATION_SOURCE_SERVICE, NavigationManagerSourceWorkflow
    )
    validation = runtime.services.require(
        NAVIGATION_DRAFT_VALIDATION_SERVICE, NavigationManagerDraftValidationWorkflow
    )
    projector = runtime.services.require(
        NAVIGATION_PROJECTION_SERVICE, SourceProjectionService
    )
    canonical_payload = NavigationConfigurationCatalog.from_document(payload).to_document()
    with client.session_transaction() as stored:
        session_values = dict(stored)
    with runtime.server.test_request_context('/manager/navigation'):
        session.update(session_values)
        draft = validation.validate_draft(payload)
        assert draft.valid, draft.issues
        source_before = source.load_current_source()
        published = source.publish_draft(payload, source_before.snapshot)
    assert published.audit.actor == 'local:jane-doe'
    assert source.load_current_source().payload == canonical_payload
    target = projector.select_current_target(NAVIGATION_SOURCE_KEY)
    assert target is not None
    projected = projector.project(target)
    assert projected.projection.payload.to_document() == canonical_payload
    assert projector.get_status(NAVIGATION_SOURCE_KEY).alignment is ProjectionAlignment.CURRENT
    return published


def test_local_manager_publishes_and_projects_into_live_navigation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    settings = _settings(tmp_path)
    local_runtime = create_operational_application_runtime(
        settings=settings,
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
    )
    unpromoted_runtime = create_operational_application_runtime(
        settings=settings,
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:unknown'),
    )
    local = local_runtime.server.test_client()
    unpromoted = unpromoted_runtime.server.test_client()
    provider = local_runtime.services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY, NavigationDefinitionProvider
    )

    assert provider.current().links == ()
    assert _document(local, '/') == 200
    assert _document(local, '/manager/navigation') == 200
    assert _document(local, '/qualification-disabled') == 200
    assert _document(unpromoted, '/') == 200
    assert _document(unpromoted, '/manager/navigation') == 403
    assert _document(unpromoted, '/qualification-public') == 403
    assert _document(unpromoted, '/qualification-basic') == 403

    first = _publish_and_project(local_runtime, local, _draft(public_enabled=True))
    assert len(provider.current().links) == 4
    assert local_runtime.services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY, NavigationDefinitionProvider
    ) is provider
    assert _document(unpromoted, '/qualification-public') == 200
    assert _document(unpromoted, '/qualification-basic') == 403
    assert _document(unpromoted, '/qualification-disabled') == 403
    assert _document(local, '/manager/navigation') == 200
    assert _document(local, '/qualification-disabled') == 200
    layout = local.get('/_dash-layout')
    assert layout.status_code == 200
    assert 'Público' in json.dumps(layout.get_json(), ensure_ascii=False)

    second = _publish_and_project(local_runtime, local, _draft(public_enabled=False))
    assert first.source.snapshot != second.source.snapshot
    assert _document(unpromoted, '/qualification-public') == 403
    assert _document(local, '/qualification-public') == 200
    assert _document(local, '/manager/navigation') == 200
    source = local_runtime.services.require(
        NAVIGATION_SOURCE_SERVICE, NavigationManagerSourceWorkflow
    )
    assert len(source.list_history().items) == 2


def test_anonymous_operational_shell_reads_shared_projection_without_identity(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    definition_provider = create_projected_navigation_definition_provider(
        stores.navigation, source_key=NAVIGATION_SOURCE_KEY
    )
    navigation_modules = create_operational_navigation_modules(
        definition_provider=definition_provider
    )
    baseline = create_local_operational_composition()
    replacements = {module.name: module for module in navigation_modules}
    anonymous_runtime = create_application_runtime(
        composition=replace(
            baseline,
            modules=tuple(
                replacements.get(module.name, module) for module in baseline.modules
            ),
        )
    )
    anonymous = anonymous_runtime.server.test_client()
    assert not anonymous_runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert _document(anonymous, '/') == 200
    assert _document(anonymous, '/qualification-public') == 403

    local_runtime = create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
    )
    local = local_runtime.server.test_client()
    assert _document(local, '/manager/navigation') == 200
    _publish_and_project(local_runtime, local, _draft(public_enabled=True))
    assert _document(anonymous, '/qualification-public') == 200
    assert _document(anonymous, '/qualification-basic') == 403
    assert _document(anonymous, '/qualification-disabled') == 403
    assert _document(anonymous, '/manager/navigation') == 403


def test_injected_profile_and_root_consume_same_live_projection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    settings = _settings(tmp_path)
    basic = compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=lambda: ManagerPrincipal(
            subject_id='trusted-basic',
            display_name='Usuario básico',
            profile_keys=('basic',),
        ),
    )
    root = compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=lambda: ManagerPrincipal(
            subject_id='trusted-root',
            display_name='Administrador root',
            profile_keys=('root',),
            access_keys=MANAGER_ACCESS_KEYS,
        ),
    )
    basic_runtime = create_operational_application_runtime(
        settings=settings, manager_dependencies=basic
    )
    root_runtime = create_operational_application_runtime(
        settings=settings, manager_dependencies=root
    )
    basic_client = basic_runtime.server.test_client()
    root_client = root_runtime.server.test_client()
    assert _document(basic_client, '/qualification-basic') == 403
    assert _document(basic_client, '/manager/navigation') == 403
    assert _document(root_client, '/manager/navigation') == 200
    assert _document(root_client, '/qualification-disabled') == 200

    local_runtime = create_operational_application_runtime(
        settings=settings,
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
    )
    local = local_runtime.server.test_client()
    assert _document(local, '/manager/navigation') == 200
    _publish_and_project(local_runtime, local, _draft(public_enabled=True))
    assert _document(basic_client, '/qualification-public') == 200
    assert _document(basic_client, '/qualification-basic') == 200
    assert _document(basic_client, '/qualification-disabled') == 403
    assert _document(root_client, '/qualification-disabled') == 200
    assert _document(root_client, '/manager/navigation') == 200
