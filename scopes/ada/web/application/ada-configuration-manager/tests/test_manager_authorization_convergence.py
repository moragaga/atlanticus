from __future__ import annotations

from ada.web.application.configuration_manager import access as access_module
from ada.web.application.configuration_manager.composition import _has_access
from ada.web.application.configuration_manager.operational import OperationalAssignmentContext
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.modules import WebModule
from atlanticus.web.source.models import SourceKey, SourceSnapshot


def _principal(
    *,
    administrative_override: bool = False,
    access_keys: tuple[str, ...] = (),
) -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='operator',
        display_name='Operator',
        access_keys=access_keys,
        administrative_override=administrative_override,
    )


def test_configuration_can_manage_uses_shared_manager_authorization() -> None:
    assert _has_access(
        _principal(administrative_override=True),
        'future.manage',
    )
    assert _has_access(
        _principal(access_keys=('tools.manage',)),
        'tools.manage',
    )
    assert not _has_access(_principal(), 'tools.manage')


def test_operational_assignment_uses_shared_manager_authorization() -> None:
    context = OperationalAssignmentContext(
        service=object(),
        promoted_users=lambda: (),
        principal=lambda: _principal(administrative_override=True),
    )

    assert context.can_manage() is True


class _AccessSource:
    source_key = SourceKey('ada-access')

    def get_current(self) -> SourceSnapshot:
        return SourceSnapshot(self.source_key, None, None)


class _ProfilesProjection:
    def get_active(self, _source_key: SourceKey):
        return None


def test_access_manager_uses_shared_manager_authorization(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class ContextStub:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(access_module, 'AdaAccessAdminWebContext', ContextStub)
    monkeypatch.setattr(
        access_module,
        'create_ada_access_admin_web_module',
        lambda _context: WebModule(name='test-access-manager'),
    )
    monkeypatch.setattr(
        access_module,
        'build_ada_access_admin_configuration',
        lambda _context: None,
    )
    principal = _principal(administrative_override=True)

    module = access_module.create_access_manager_module(
        source=_AccessSource(),
        projection=object(),
        profiles_projection=_ProfilesProjection(),
        profiles_source_key=SourceKey('profiles-configuration'),
        principal_provider=lambda: principal,
        audit_actor_provider=lambda: principal.subject_id,
        source_name='Source',
        projection_name='Projection',
    )

    assert module.access_key == access_module.ACCESS_MANAGER_ACCESS_KEY
    can_manage = captured['can_manage']
    assert callable(can_manage)
    assert can_manage() is True
