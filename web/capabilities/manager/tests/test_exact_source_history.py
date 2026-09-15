from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ExactSourceHistoryReadResult,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerProjectionError,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import (
    Digest,
    HistoryPage,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
)


def _release(value: str, minute: int) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 15, 20, minute, tzinfo=UTC),
    )


class _History:
    def __init__(self) -> None:
        self.release = _release('release-1', 0)
        self.page = HistoryPage(
            items=(
                SourceReleaseSummary(
                    release_ref=self.release,
                    content_hash=Digest('sha256', 'historyhash'),
                ),
            )
        )
        self.loaded: list[SourceReleaseRef] = []

    def list_history_exact(self, *, limit: int = 20) -> HistoryPage:
        assert limit == 20
        return self.page

    def load_history_release_exact(
        self,
        release_ref: SourceReleaseRef,
    ) -> ExactSourceHistoryReadResult:
        self.loaded.append(release_ref)
        return ExactSourceHistoryReadResult(
            release_ref=release_ref,
            payload={'users': [], 'profiles': []},
        )


def _coordinator(workflow: object) -> ManagerProjectionCoordinator:
    module = ManagerModule(
        key='users',
        group_key='configuration',
        title='Usuarios',
        route='/users',
        order=10,
        layout=lambda _services: None,
        draft_validation_service='users.validation',
        exact_source_reader_service='users.reader',
        exact_source_workflow_service='users.source',
        exact_source_history_service='users.history',
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('users.history', workflow)
    return ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )


def test_exact_history_routes_without_legacy_lifecycle() -> None:
    workflow = _History()
    coordinator = _coordinator(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    page = coordinator.list_history('users', principal)
    result = coordinator.load_history_release_exact(
        'users',
        principal,
        workflow.release,
    )

    assert page is workflow.page
    assert coordinator.can_load_history('users', principal) is True
    assert result.release_ref == workflow.release
    assert result.payload == {'users': [], 'profiles': []}
    assert workflow.loaded == [workflow.release]


class _BrokenHistory(_History):
    def load_history_release_exact(
        self,
        release_ref: SourceReleaseRef,
    ) -> ExactSourceHistoryReadResult:
        return ExactSourceHistoryReadResult(
            release_ref=_release('wrong-release', 1),
            payload={},
        )


def test_exact_history_rejects_different_release_identity() -> None:
    workflow = _BrokenHistory()
    coordinator = _coordinator(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    with pytest.raises(ManagerProjectionError, match='different source release'):
        coordinator.load_history_release_exact(
            'users',
            principal,
            workflow.release,
        )
