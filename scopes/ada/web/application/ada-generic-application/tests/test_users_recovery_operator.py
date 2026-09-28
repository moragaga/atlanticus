from __future__ import annotations

import ast
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from ada.web.application.generic import users_recovery_operator as operator
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.recovery import UsersRecoveryConflictError


class FakeService:
    def __init__(self):
        self.events = []
        self.preview = SimpleNamespace(
            registry_version='v1',
            content_digest='digest-one',
            approved_users=(
                SimpleNamespace(
                    user_id='approved',
                    to_document=lambda: {
                        'user_id': 'approved',
                        'profile_key': 'basic',
                        'enabled': True,
                    },
                ),
            ),
            candidate_user_ids=('candidate',),
        )
        self.validation = SimpleNamespace(
            snapshot=SimpleNamespace(
                snapshot_id='snap-one',
                content_digest='digest-one',
                origin_environment='dev',
            ),
            registry_state=SimpleNamespace(value='empty'),
            can_restore=True,
            registry_conflict_user_ids=(),
            differences=(
                SimpleNamespace(
                    user_id='approved',
                    kind=SimpleNamespace(value='missing'),
                    fields=(),
                ),
            ),
        )

    @property
    def replace_validation(self):
        plan = SimpleNamespace(
            registry_write_required=True,
            registry_discarded_ids=('candidate',),
            create_ids=('approved',),
            update_ids=(),
            delete_ids=('unexpected',),
            unchanged_ids=(),
        )
        return SimpleNamespace(
            recovery=self.validation,
            can_replace=True,
            plan=plan,
        )

    def validate_replace(self, snapshot_id):
        self.events.append(('validate_replace', snapshot_id))
        return self.replace_validation

    def replace_approved(self, **kwargs):
        self.events.append(('replace_approved', kwargs))
        return self.replace_validation

    def preview_capture(self):
        self.events.append(('preview',))
        return self.preview

    def capture(self, **kwargs):
        self.events.append(('capture', kwargs))
        return SimpleNamespace(
            snapshot_id='snap-one',
            content_digest='digest-one',
            origin_environment='dev',
            users=self.preview.approved_users,
        )

    def validate(self, snapshot_id):
        self.events.append(('validate', snapshot_id))
        return self.validation

    def restore(self, **kwargs):
        self.events.append(('restore', kwargs))
        return self.validation


@pytest.fixture
def wiring(monkeypatch):
    service = FakeService()
    opened = []
    access = SimpleNamespace(get_active=lambda key: object())
    runtime = SimpleNamespace(stores=SimpleNamespace(access=access))
    settings = SimpleNamespace(environment=SimpleNamespace(is_local=True))
    monkeypatch.setattr(operator, 'AdaGenericSettings', lambda: settings)
    startup = SimpleNamespace(provider='durable')
    monkeypatch.setattr(operator, 'ManagerStartupOptions', lambda: startup)
    monkeypatch.setattr(operator, 'resolve_durable_manager_configuration', lambda _: 'config')

    @contextmanager
    def open_manager(_settings):
        opened.append('open')
        yield runtime
        opened.append('close')

    monkeypatch.setattr(operator, 'open_durable_manager', open_manager)
    monkeypatch.setattr(operator, '_service', lambda **kwargs: service)
    return SimpleNamespace(
        service=service, opened=opened, runtime=runtime, settings=settings, startup=startup
    )


def common(action):
    return [action, '--identity-realm', 'dev-tenant', '--environment', 'dev']


def capture_args():
    return [
        *common('capture'),
        '--expected-digest',
        'digest-one',
        '--operator-id',
        'operator',
        '--approval-reference',
        'manual-approval',
    ]


def restore_args():
    return [
        *common('restore'),
        '--snapshot-id',
        'snap-one',
        '--expected-digest',
        'digest-one',
        '--operator-id',
        'operator',
        '--approval-reference',
        'manual-approval',
    ]


def test_preview_reports_candidates_separately_without_mutation(wiring, capsys):
    assert operator.main(common('preview')) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['approved_user_ids'] == ['approved']
    assert result['approved_users'] == [
        {'user_id': 'approved', 'profile_key': 'basic', 'enabled': True}
    ]
    assert result['candidate_user_ids'] == ['candidate']
    assert result['snapshot_digest'] == 'digest-one'
    assert wiring.service.events == [('preview',)]
    assert wiring.opened == ['open', 'close']


def test_capture_requires_confirmation_before_connections(wiring):
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        operator.main(capture_args())
    assert wiring.opened == []


def test_capture_refuses_different_preview_digest(wiring):
    with pytest.raises(UsersRecoveryConflictError, match='digest'):
        operator.main([*capture_args(), '--expected-digest', 'obsolete', '--confirm-capture'])
    assert not any(event[0] == 'capture' for event in wiring.service.events)


def test_capture_uses_explicit_approval_and_excludes_candidates(wiring, capsys):
    assert operator.main([*capture_args(), '--confirm-capture']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['approved_count'] == 1
    assert result['snapshot_id'] == 'snap-one'
    saved = wiring.service.events[-1][1]
    assert saved['approved_user_ids'] == ('approved',)
    assert saved['operator_id'] == 'operator'
    assert saved['approval_reference'] == 'manual-approval'
    assert saved['confirmed'] is True


def test_validation_reports_differences_without_restore(wiring, capsys):
    assert operator.main([*common('validate'), '--snapshot-id', 'snap-one']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['can_restore'] is True
    assert result['registry_state'] == 'empty'
    assert result['differences'] == [
        {'user_id': 'approved', 'kind': 'missing', 'fields': []}
    ]
    assert wiring.service.events == [('validate', 'snap-one')]


@pytest.mark.parametrize(
    'flag', ('--confirm-restore', '--confirm-maintenance', '--reviewed-revocations')
)
def test_restore_requires_every_confirmation_before_connections(wiring, flag):
    flags = {'--confirm-restore', '--confirm-maintenance', '--reviewed-revocations'}
    with pytest.raises(UsersRecoveryConflictError, match='maintenance'):
        operator.main([*restore_args(), *(flags - {flag})])
    assert wiring.opened == []


def test_restore_refuses_unpublished_access(wiring):
    wiring.runtime.stores.access.get_active = lambda key: None
    with pytest.raises(UsersRecoveryConflictError, match='Access'):
        operator.main([
            *restore_args(), '--confirm-restore', '--confirm-maintenance', '--reviewed-revocations'
        ])
    assert wiring.service.events == []


def test_restore_refuses_conflicted_target(wiring):
    wiring.service.validation.can_restore = False
    with pytest.raises(UsersRecoveryConflictError, match='not empty'):
        operator.main([
            *restore_args(), '--confirm-restore', '--confirm-maintenance', '--reviewed-revocations'
        ])
    assert not any(event[0] == 'restore' for event in wiring.service.events)


def test_restore_refuses_changed_snapshot_digest(wiring):
    wiring.service.validation.snapshot.content_digest = 'different'
    with pytest.raises(UsersRecoveryConflictError, match='digest'):
        operator.main([
            *restore_args(), '--confirm-restore', '--confirm-maintenance', '--reviewed-revocations'
        ])
    assert not any(event[0] == 'restore' for event in wiring.service.events)


def test_restore_audits_distinct_operation_and_returns_validation(wiring, capsys):
    assert operator.main([
        *restore_args(), '--confirm-restore', '--confirm-maintenance', '--reviewed-revocations'
    ]) == 0
    started, completed = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert started['operation_id'] == completed['operation_id']
    assert started['stage'] == 'starting'
    assert completed['stage'] == 'completed'
    assert completed['can_restore'] is True
    saved = wiring.service.events[-1][1]
    assert saved['confirmed_digest'] == 'digest-one'
    assert saved['operation_id'] == completed['operation_id']
    assert saved['confirmed'] is True
    assert saved['maintenance_confirmed'] is True


@pytest.mark.parametrize('provider', ('auto', 'local', 'disabled'))
def test_operator_requires_explicit_durable_provider(wiring, provider):
    wiring.startup.provider = provider
    with pytest.raises(UsersRecoveryConflictError, match='Durable Manager'):
        operator.main(common('preview'))
    assert wiring.opened == []


def test_production_environment_is_rejected_without_access(wiring):
    wiring.settings.environment.is_local = False
    with pytest.raises(UsersRecoveryConflictError, match='local'):
        operator.main(common('preview'))
    assert wiring.opened == []


def test_composition_reuses_application_namespace_and_recovery_prefixes(monkeypatch):
    received = {}

    class FakeSnapshotStore:
        def __init__(self, **kwargs):
            received['snapshot'] = kwargs

    class FakeAuditStore:
        def __init__(self, **kwargs):
            received['audit'] = kwargs

    class FakeRecoveryService:
        def __init__(self, **kwargs):
            received['service'] = kwargs

    monkeypatch.setattr(operator, 'BlobApprovedUsersSnapshotStore', FakeSnapshotStore)
    monkeypatch.setattr(operator, 'BlobUsersRecoveryAuditStore', FakeAuditStore)
    monkeypatch.setattr(operator, 'UsersApprovedRecoveryService', FakeRecoveryService)
    namespace = SimpleNamespace(
        application_namespace='app-one',
        application_blob_name=lambda relative: f'app-one/{relative}',
    )
    client = object()
    active = SimpleNamespace(payload=ProfileCatalog())
    profiles = SimpleNamespace(get_active=lambda key: active)
    stores = SimpleNamespace(users_registry=object(), users_promoted=object(), profiles=profiles)
    deployment = SimpleNamespace(
        stores=stores,
        resources=SimpleNamespace(users_registry=SimpleNamespace(
            connection_ref='storage', container_name='configuration'
        )),
        connections=SimpleNamespace(storage={'storage': client}),
    )
    operator._service(
        resolved=SimpleNamespace(namespace=namespace),
        deployment=deployment,
        identity_realm='realm',
        environment='dev',
    )
    assert received['snapshot']['client'] is client
    assert received['snapshot']['prefix'] == 'app-one/users/recovery/snapshots'
    assert received['audit']['prefix'] == 'app-one/users/recovery/audit'
    assert received['service']['registry'] is stores.users_registry
    assert received['service']['promoted'] is stores.users_promoted
    assert isinstance(received['service']['profiles'](), ProfileCatalog)
    assert received['service']['application_key'] == 'app-one'
    profiles.get_active = lambda key: None
    with pytest.raises(UsersRecoveryConflictError, match='Profiles'):
        received['service']['profiles']()


def test_operator_pedagogical_mirror_preserves_behavior():
    root = Path(__file__).resolve().parents[1]
    relative = Path('ada/web/application/generic/users_recovery_operator.py')
    product = (root / 'src' / relative).read_text(encoding='utf-8')
    commented = (root / 'commented' / relative).read_text(encoding='utf-8')
    assert ast.dump(ast.parse(product)) == ast.dump(ast.parse(commented))


def replacement_args():
    return [
        *common('replace'),
        '--snapshot-id', 'snap-one',
        '--expected-digest', 'digest-one',
        '--operator-id', 'operator',
        '--approval-reference', 'manual-approval',
    ]


def test_inspect_replace_does_not_require_access_projection(wiring, capsys):
    wiring.runtime.stores.access.get_active = lambda _key: None
    assert operator.main([*common('inspect-replace'), '--snapshot-id', 'snap-one']) == 0
    document = json.loads(capsys.readouterr().out)
    assert document['can_replace'] is True
    assert document['create_user_ids'] == ['approved']
    assert document['delete_user_ids'] == ['unexpected']
    assert document['registry_discarded_user_ids'] == ['candidate']
    assert wiring.service.events == [('validate_replace', 'snap-one')]


@pytest.mark.parametrize(
    'missing', ('--confirm-replace', '--confirm-maintenance', '--reviewed-revocations'),
)
def test_replace_requires_every_confirmation_before_connections(wiring, missing):
    flags = {'--confirm-replace', '--confirm-maintenance', '--reviewed-revocations'}
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        operator.main([*replacement_args(), *(flags - {missing})])
    assert wiring.opened == []


def test_replace_uses_separate_authorized_operation_and_returns_result(wiring, capsys):
    wiring.runtime.stores.access.get_active = lambda _key: None
    assert operator.main([
        *replacement_args(), '--confirm-replace', '--confirm-maintenance',
        '--reviewed-revocations',
    ]) == 0
    started, completed = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert started['operation_id'] == completed['operation_id']
    assert completed['mode'] == 'replace'
    assert completed['stage'] == 'completed'
    assert wiring.service.events[-1][0] == 'replace_approved'
    assert wiring.service.events[-1][1]['confirmed'] is True
    assert wiring.service.events[-1][1]['maintenance_confirmed'] is True
    assert wiring.service.events[-1][1]['revocations_reviewed'] is True
