from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ada.web.application.generic import users_recovery_operator as operator
from atlanticus.web.users.recovery import UsersRecoveryConflictError


class FakeService:
    def __init__(self):
        self.events = []
        self.user = SimpleNamespace(
            user_id='runtime-user',
            to_document=lambda: {'identity': {'user_id': 'runtime-user'}},
        )
        self.preview = SimpleNamespace(content_digest='digest-one', users=(self.user,))
        self.validation = SimpleNamespace(
            snapshot=SimpleNamespace(
                snapshot_id='snapshot-1',
                content_digest='digest-one',
                origin_environment='local:test',
            ),
            create_ids=('runtime-user',),
            update_ids=(),
            delete_ids=('obsolete',),
            differences=(
                SimpleNamespace(
                    user_id='runtime-user',
                    kind=SimpleNamespace(value='missing'),
                    fields=(),
                ),
            ),
        )

    def preview_capture(self):
        self.events.append(('preview',))
        return self.preview

    def capture(self, **kwargs):
        self.events.append(('capture', kwargs))
        return SimpleNamespace(
            snapshot_id='snapshot-1',
            content_digest='digest-one',
            origin_environment='local:test',
            users=(self.user,),
        )

    def validate_replace(self, snapshot_id):
        self.events.append(('validate', snapshot_id))
        return self.validation

    def replace_snapshot(self, **kwargs):
        self.events.append(('replace', kwargs))
        return SimpleNamespace(
            snapshot=self.validation.snapshot,
            create_ids=(),
            update_ids=(),
            delete_ids=(),
            differences=(),
        )


@pytest.fixture
def wiring(monkeypatch):
    service = FakeService()
    opened = []
    settings = SimpleNamespace(environment=SimpleNamespace(is_local=True))
    startup = SimpleNamespace(provider='durable')
    runtime = SimpleNamespace(stores=SimpleNamespace(users_recovery=lambda: service))
    monkeypatch.setattr(operator, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(operator, 'ManagerStartupOptions', lambda: startup)

    @contextmanager
    def open_manager(_settings):
        opened.append('open')
        yield runtime
        opened.append('close')

    monkeypatch.setattr(operator, 'open_durable_manager', open_manager)
    monkeypatch.setattr(operator, '_service', lambda _deployment: service)
    return SimpleNamespace(service=service, opened=opened, settings=settings, startup=startup)


def test_preview_reports_materialized_runtime_users(wiring, capsys):
    assert operator.main(['preview']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['runtime_user_ids'] == ['runtime-user']
    assert result['snapshot_digest'] == 'digest-one'


def test_capture_requires_confirmation_before_opening_resources(wiring):
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        operator.main(
            [
                'capture',
                '--expected-digest',
                'digest-one',
                '--operator-id',
                'operator',
                '--approval-reference',
                'ticket',
            ]
        )
    assert wiring.opened == []


def test_capture_validates_digest_and_saves_complete_runtime(wiring, capsys):
    assert (
        operator.main(
            [
                'capture',
                '--expected-digest',
                'digest-one',
                '--operator-id',
                'operator',
                '--approval-reference',
                'ticket',
                '--confirm-capture',
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result['runtime_user_count'] == 1
    assert wiring.service.events[-1][0] == 'capture'


def test_validate_reports_create_update_delete_plan(wiring, capsys):
    assert operator.main(['validate', '--snapshot-id', 'snapshot-1']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['create_user_ids'] == ['runtime-user']
    assert result['delete_user_ids'] == ['obsolete']


@pytest.mark.parametrize(
    'missing',
    ('--confirm-replace', '--confirm-maintenance', '--reviewed-revocations'),
)
def test_replace_requires_all_safety_confirmations(wiring, missing):
    flags = {'--confirm-replace', '--confirm-maintenance', '--reviewed-revocations'}
    args = [
        'replace',
        '--snapshot-id',
        'snapshot-1',
        '--operator-id',
        'operator',
        '--approval-reference',
        'ticket',
        *(flags - {missing}),
    ]
    with pytest.raises(UsersRecoveryConflictError, match='maintenance'):
        operator.main(args)
    assert wiring.opened == []


def test_replace_calls_runtime_snapshot_replacement(wiring, capsys):
    assert (
        operator.main(
            [
                'replace',
                '--snapshot-id',
                'snapshot-1',
                '--operator-id',
                'operator',
                '--approval-reference',
                'ticket',
                '--confirm-replace',
                '--confirm-maintenance',
                '--reviewed-revocations',
            ]
        )
        == 0
    )
    started, completed = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert started['stage'] == 'starting'
    assert completed['stage'] == 'completed'
    assert wiring.service.events[-1][0] == 'replace'


def test_operator_rejects_non_local_or_non_durable_before_opening_resources(wiring):
    wiring.settings.environment.is_local = False
    with pytest.raises(UsersRecoveryConflictError, match='local'):
        operator.main(['preview'])
    wiring.settings.environment.is_local = True
    wiring.startup.provider = 'local'
    with pytest.raises(UsersRecoveryConflictError, match='Durable Manager'):
        operator.main(['preview'])
    assert wiring.opened == []
