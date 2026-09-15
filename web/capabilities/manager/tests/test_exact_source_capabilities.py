from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    DraftValidationResult,
    ExactSourceReadResult,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerProjectionError,
    ProjectionAuditRecord,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId('release-1'),
                published_at_utc=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', 'hash-release-1'),
        ),
        concurrency_token=ConcurrencyToken('etag-1'),
    )


def _validation_result(payload: dict[str, object]) -> DraftValidationResult:
    return DraftValidationResult(
        draft_revision=str(payload['revision']),
        valid=True,
        audit=ProjectionAuditRecord(
            actor='Admin',
            occurred_at=datetime(2026, 9, 15, 12, 5, tzinfo=UTC),
        ),
    )


class Validator:
    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        return _validation_result(payload)


class Reader:
    def __init__(self) -> None:
        self.result = ExactSourceReadResult(
            snapshot=_snapshot(),
            payload={'users': [], 'profiles': []},
        )

    def load_current_source_exact(self) -> ExactSourceReadResult:
        return self.result


class InvalidService:
    pass


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal('local', 'Administrador local', is_local=True)


def _coordinator(
    *,
    exact_source: bool,
    validator: object | None = None,
    reader: object | None = None,
    lifecycle: object | None = None,
) -> ManagerProjectionCoordinator:
    module = ManagerModule(
        key='users',
        group_key='configuration',
        title='Usuarios',
        route='/users',
        order=10,
        layout=lambda _services: None,
        workflow_service='users.workflow',
        exact_source_workflow_service='users.exact-source' if exact_source else None,
        draft_validation_service='users.validation' if validator is not None else None,
        exact_source_reader_service='users.reader' if reader is not None else None,
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('users.workflow', lifecycle or InvalidService())
    if validator is not None:
        services.add('users.validation', validator)
    if reader is not None:
        services.add('users.reader', reader)
    return ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )


def test_exact_source_read_result_requires_payload_when_source_exists() -> None:
    with pytest.raises(
        ManagerProjectionError,
        match='include payload exactly when source exists',
    ):
        ExactSourceReadResult(snapshot=_snapshot(), payload=None)


def test_exact_source_read_result_rejects_payload_without_source() -> None:
    empty = SourceSnapshot(
        source_key=SourceKey('users'),
        current=None,
        concurrency_token=None,
    )

    with pytest.raises(
        ManagerProjectionError,
        match='include payload exactly when source exists',
    ):
        ExactSourceReadResult(snapshot=empty, payload={'users': []})


def test_exact_source_reader_is_resolved_independently_from_lifecycle() -> None:
    reader = Reader()
    coordinator = _coordinator(
        exact_source=True,
        validator=Validator(),
        reader=reader,
        lifecycle=InvalidService(),
    )

    assert coordinator.load_current_source_exact('users', _principal()) == reader.result


def test_exact_source_reader_requires_explicit_service() -> None:
    coordinator = _coordinator(
        exact_source=True,
        validator=Validator(),
        reader=None,
        lifecycle=Reader(),
    )

    with pytest.raises(
        ManagerProjectionError,
        match='does not declare an exact source reader service',
    ):
        coordinator.load_current_source_exact('users', _principal())


def test_exact_source_validation_uses_explicit_validator() -> None:
    coordinator = _coordinator(
        exact_source=True,
        validator=Validator(),
        reader=Reader(),
        lifecycle=InvalidService(),
    )

    result = coordinator.validate_draft(
        'users',
        _principal(),
        {'revision': 'workspace-1'},
    )

    assert result.valid is True
    assert result.draft_revision == 'workspace-1'


def test_exact_source_validation_does_not_fall_back_to_legacy_workflow() -> None:
    coordinator = _coordinator(
        exact_source=True,
        validator=None,
        reader=Reader(),
        lifecycle=Validator(),
    )

    with pytest.raises(
        ManagerProjectionError,
        match='does not declare a draft validation service',
    ):
        coordinator.validate_draft(
            'users',
            _principal(),
            {'revision': 'workspace-1'},
        )


def test_legacy_module_keeps_validation_via_workflow_service() -> None:
    coordinator = _coordinator(
        exact_source=False,
        lifecycle=Validator(),
    )

    result = coordinator.validate_draft(
        'users',
        _principal(),
        {'revision': 'legacy-1'},
    )

    assert result.valid is True
    assert result.draft_revision == 'legacy-1'


def test_explicit_validation_service_rejects_invalid_contract() -> None:
    coordinator = _coordinator(
        exact_source=True,
        validator=InvalidService(),
        reader=Reader(),
    )

    with pytest.raises(
        ManagerProjectionError,
        match='draft validation workflow has an invalid contract',
    ):
        coordinator.validate_draft(
            'users',
            _principal(),
            {'revision': 'workspace-1'},
        )
