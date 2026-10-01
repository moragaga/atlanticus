from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.configuration_manager.composition import (
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    create_local_configuration_manager_dependencies,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE,
    OPERATIONAL_CATALOG_PROJECTION_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_READER_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_SERVICE,
    compose_operational_catalog_manager_contracts,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationService,
    OperationalReferenceError,
    Position,
    assignment_source_key,
)
from atlanticus.web.manager import (
    DraftValidationWorkflow,
    ManagerWorkspaceBinding,
    SourceHistoryWorkflow,
    SourcePublicationWorkflow,
    SourceReaderWorkflow,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore

USER_ID = 'user:' + 'a' * 24


class _Users:
    def get(self, user_id):
        return SimpleNamespace(user_id=user_id) if user_id == USER_ID else None


def _contracts(tmp_path):
    source_store = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projections = InProcessProjectionStore()
    service = OperationalIdentificationService(
        source_store=source_store,
        projections=projections,
        users=_Users(),
    )
    contracts = compose_operational_catalog_manager_contracts(
        service=service,
        source_store=source_store,
        projection_store=projections,
        audit_actor_provider=lambda: 'operator',
    )
    return contracts, service, projections


def test_catalog_contracts_use_standard_manager_workflows(tmp_path):
    contracts, _service, _projection = _contracts(tmp_path)
    assert isinstance(contracts.source, SourceReaderWorkflow)
    assert isinstance(contracts.source, SourcePublicationWorkflow)
    assert isinstance(contracts.source, SourceHistoryWorkflow)
    assert isinstance(contracts.validation, DraftValidationWorkflow)
    assert contracts.source.get_source_snapshot().source_key == CATALOG_SOURCE_KEY
    assert contracts.source.load_current_source().payload is None


def test_editor_preserves_draft_identity_without_implicit_publication(tmp_path):
    contracts, service, _projection = _contracts(tmp_path)
    editor = contracts.editor
    initial_payload = OperationalCatalog().to_document()
    document, generated = editor.add_position(initial_payload, label='Ingeniero de turno')
    assert generated.startswith('position_')
    assert len(generated) == len('position_') + 32
    assert service.catalog_for_edit()[0].current is None
    edited = editor.update_position(
        document,
        position_id=generated,
        label='Ingeniero de sala',
        active=False,
    )
    assert edited['positions'][0]['id'] == generated
    assert edited['positions'][0]['active'] is False

    workspace = ManagerWorkspaceBinding(
        owner_subject_id_provider=lambda: 'operator',
        source_key=contracts.source.source_key,
        source_snapshot_provider=contracts.source.get_source_snapshot,
    )
    first_draft = workspace.save_payload(None, document)
    second_draft = workspace.save_payload(first_draft, edited)
    assert workspace.load_payload(second_draft) == edited
    assert second_draft['source_snapshot']['source_key'] == CATALOG_SOURCE_KEY.value
    assert service.catalog_for_edit()[0].current is None

    validation = contracts.validation.validate_draft(edited)
    assert validation.valid is True
    assert validation.draft_revision == second_draft['revision']
    published = contracts.source.publish_draft(edited, contracts.source.get_source_snapshot())
    assert published.source.snapshot.current is not None
    assert service.catalog_for_edit()[1].position(generated).label == 'Ingeniero de sala'
    assert service.catalog_for_read().positions == ()

    target = contracts.projection.select_current_target(CATALOG_SOURCE_KEY)
    assert target is not None
    contracts.projection.project(target)
    assert service.catalog_for_read().position(generated) is not None


def test_validation_rejects_duplicates_and_legacy_position_removal(tmp_path):
    contracts, service, _projection = _contracts(tmp_path)
    original, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('original', 'Operador'),)),
        actor='operator',
        expected=original,
    )
    invalid = OperationalCatalog().to_document()
    result = contracts.validation.validate_draft(invalid)
    assert result.valid is False
    assert result.issues[0].code == 'ada.operational.catalog.invalid'
    with pytest.raises(OperationalReferenceError):
        contracts.source.publish_draft(invalid, contracts.source.get_source_snapshot())

    duplicate = OperationalCatalog().to_document()
    duplicate['positions'] = [
        {'id': 'a', 'label': 'Operador', 'active': True},
        {'id': 'b', 'label': 'OPERADOR', 'active': True},
    ]
    result = contracts.validation.validate_draft(duplicate)
    assert result.valid is False


def test_publication_requires_matching_source_snapshot_and_history_is_exact(tmp_path):
    contracts, service, _projection = _contracts(tmp_path)
    before = contracts.source.get_source_snapshot()
    first, generated = contracts.editor.add_position(
        OperationalCatalog().to_document(),
        label='Operador',
    )
    first_pub = contracts.source.publish_draft(first, before)
    with pytest.raises(OperationalReferenceError, match='changed'):
        contracts.source.publish_draft(first, before)
    second = contracts.editor.update_position(
        first,
        position_id=generated,
        label='Supervisor',
        active=True,
    )
    contracts.source.publish_draft(second, first_pub.source.snapshot)
    history = contracts.source.list_history()
    assert len(history.items) == 2
    old = contracts.source.load_history_release(first_pub.source.release.release_ref)
    assert old.payload['positions'][0]['label'] == 'Operador'
    assert contracts.source.load_current_source().payload['positions'][0]['label'] == 'Supervisor'
    assert service.catalog_for_read().positions == ()


def test_catalog_and_individual_assignment_remain_independent(tmp_path):
    contracts, service, projections = _contracts(tmp_path)
    payload, position_id = contracts.editor.add_position(
        OperationalCatalog().to_document(),
        label='Operador',
    )
    contracts.source.publish_draft(payload, contracts.source.get_source_snapshot())
    target = contracts.projection.select_current_target(CATALOG_SOURCE_KEY)
    assert target is not None
    contracts.projection.project(target)

    individual_snapshot, _ = service.assignment_for_edit(USER_ID)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_ID, area_id='mina', position_id=position_id),
        actor='operator',
        expected=individual_snapshot,
    )
    assert projections.get_active(assignment_source_key(USER_ID)) is None
    service.project_current(assignment_source_key(USER_ID))
    assert service.assignment_for_read(USER_ID).position_id == position_id
    assert service.catalog_for_read().position(position_id) is not None
    assert len(contracts.source.list_history().items) == 1


def test_local_wiring_exposes_operational_catalog_as_manager_module(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    contracts = dependencies.operational_catalog_contracts
    assert contracts is not None
    definition = build_configuration_manager_surface(dependencies)
    assert all(entry.key != 'operational-identification' for entry in definition.entries)
    operational = tuple(
        module for module in definition.modules if module.key == 'operational-identification'
    )
    assert len(operational) == 1
    module = operational[0]
    assert module.title == 'Datos operacionales'
    assert module.primary_view_title == 'Catálogo de cargos'
    assert module.default_primary_view == 'companion'
    assert module.companion_view is not None
    assert module.companion_view.title == 'Asignaciones'
    assert module.source_name == dependencies.operational_source_name
    assert module.projection_name == dependencies.operational_projection_name

    services_module = next(
        module
        for module in definition.web_modules
        if module.name == 'ada-configuration-manager-services'
    )
    services = ServiceRegistry()
    services_module.register_services(services)
    assert services.require(OPERATIONAL_CATALOG_SOURCE_SERVICE) is contracts.source
    assert services.require(OPERATIONAL_CATALOG_SOURCE_READER_SERVICE) is contracts.source
    assert services.require(OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE) is contracts.source
    assert services.require(OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE) is contracts.validation
    assert services.require(OPERATIONAL_CATALOG_PROJECTION_SERVICE) is contracts.projection
