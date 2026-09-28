from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from ada.web.application.generic.master_projection.apply import (
    MasterApplyError,
    MasterApplyOutcome,
    MasterApplyResult,
)
from ada.web.application.generic.master_projection.plan import (
    ProjectionPlanEntry,
    ProjectionPlanState,
)
from ada.web.application.generic.master_projection.web import MasterProjectionWebBinding
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

NOW = datetime(2026, 9, 28, tzinfo=UTC)
KEY = SourceKey('profiles-configuration')


class MaterialReader:
    def __init__(self, actions=('projection.preview', 'projection.apply')) -> None:
        self.actions = actions
        self.status = 'PRESENT'
        self.digest = 'a' * 64
        self.calls = 0

    def inspect(self):
        return self.status

    def fingerprint(self):
        return self.digest

    def unlock(self, *, service_user, password, application_namespace, environment):
        self.calls += 1
        if service_user != 'operator' or password != 'valid-long-password':
            raise ValueError('Invalid credentials')
        return SimpleNamespace(
            material_id='material-1', service_user=service_user,
            application_namespace=application_namespace, environment=environment,
            allowed_actions=self.actions,
        )


class Planner:
    def __init__(self) -> None:
        self.release = 'release-1'
        self.state = ProjectionPlanState.NEVER_PROJECTED
        self.error = False
        self.calls = 0

    def inspect(self):
        self.calls += 1
        if self.error:
            raise ConnectionError('private-storage-endpoint')
        target = ProjectionTarget(KEY, SourceReleaseRef(SourceReleaseId(self.release), NOW))
        entry = ProjectionPlanEntry(
            key=KEY, state=self.state, source_release=target.source_release,
            current_target=target if self.state in (
                ProjectionPlanState.NEVER_PROJECTED, ProjectionPlanState.OUTDATED,
                ProjectionPlanState.CURRENT,
            ) else None,
            projected_target=None, prerequisites=(),
            blocked_by=() if self.state is not ProjectionPlanState.BLOCKED else (SourceKey('tools'),),
        )
        return SimpleNamespace(
            entries=(entry,),
            users=SimpleNamespace(
                state=SimpleNamespace(value='SNAPSHOT_SELECTION_REQUIRED'),
                snapshot_ids=('approved-1',),
            ),
        )


class Executor:
    def __init__(self, planner) -> None:
        self.planner = planner
        self.calls = []
        self.failure = None

    def apply(self, *, source_key, expected_target):
        self.calls.append((source_key, expected_target))
        if self.failure == 'UNEXPECTED_ERROR':
            raise RuntimeError('private-backend-details')
        if self.failure is not None:
            raise MasterApplyError('private-secret', reason=self.failure)
        self.planner.state = ProjectionPlanState.CURRENT
        return MasterApplyResult(source_key, expected_target, MasterApplyOutcome.APPLIED)


@pytest.fixture
def surface(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    reader = MaterialReader()
    planner = Planner()
    executor = Executor(planner)
    server = Flask(__name__)
    server.testing = True
    module = MasterProjectionWebBinding(
        application_namespace='test-app', environment='local', planner=planner,
        reader=reader, executor=executor,
    ).module()
    module.register_middlewares(server, None)
    module.register_routes(server, None)
    return server, reader, planner, executor


def _field(html, field):
    match = re.search(r'name="' + field + r'" value="([^"]+)"', html)
    assert match, field
    return match[1]


def _login(client):
    token = _field(client.get('/master-projection').get_data(as_text=True), 'csrf')
    result = client.post('/master-projection', data={
        'csrf': token, 'service_user': 'operator', 'password': 'valid-long-password',
    })
    assert result.status_code == 303


def _prepare(client, key='profiles-configuration', csrf=None):
    page = client.get('/master-projection').get_data(as_text=True)
    token = csrf if csrf is not None else _field(page, 'csrf')
    return client.post('/master-projection', data={
        'csrf': token, 'intent': 'prepare', 'source_key': key,
    })


def _confirm(client, nonce=None, csrf=None):
    page = client.get('/master-projection').get_data(as_text=True)
    token = csrf if csrf is not None else _field(page, 'csrf')
    selected = nonce if nonce is not None else _field(page, 'nonce')
    return client.post('/master-projection', data={
        'csrf': token, 'intent': 'confirm', 'nonce': selected,
    })


def test_individual_confirmation_executes_one_selection_and_refreshes_plan(surface):
    server, _, planner, executor = surface
    client = server.test_client()
    _login(client)
    page = client.get('/master-projection').get_data(as_text=True)
    assert 'Preparar despliegue' in page
    assert 'Confirmar despliegue' not in page
    assert 'users.replace' not in page
    assert _prepare(client).status_code == 303
    assert executor.calls == []
    prepared = client.get('/master-projection').get_data(as_text=True)
    assert 'Confirmar despliegue' in prepared
    assert 'release-1' in prepared
    assert _confirm(client).status_code == 303
    assert len(executor.calls) == 1
    assert executor.calls[0][0] == KEY
    assert executor.calls[0][1].source_release.release_id == SourceReleaseId('release-1')
    assert planner.state is ProjectionPlanState.CURRENT
    completed = client.get('/master-projection').get_data(as_text=True)
    assert 'Proyección aplicada: profiles-configuration.' in completed
    assert 'Preparar despliegue' not in completed
    assert 'Confirmar despliegue' not in completed


def test_anonymous_requests_never_inspect_or_write(surface):
    server, _, planner, executor = surface
    client = server.test_client()
    assert client.get('/master-projection').status_code == 200
    assert client.post('/master-projection', data={
        'intent': 'prepare', 'source_key': KEY.value,
    }).status_code == 403
    assert planner.calls == 0
    assert executor.calls == []


def test_preview_only_material_never_enables_write(surface):
    server, reader, _, executor = surface
    reader.actions = ('projection.preview',)
    client = server.test_client()
    _login(client)
    html = client.get('/master-projection').get_data(as_text=True)
    assert 'exclusivamente de lectura' in html
    assert 'Preparar despliegue' not in html
    assert _prepare(client).status_code == 403
    assert executor.calls == []


def test_unwired_executor_never_enables_write(surface):
    server, reader, planner, _ = surface
    alternative = Flask(__name__)
    alternative.testing = True
    module = MasterProjectionWebBinding(
        application_namespace='test-app', environment='local', planner=planner,
        reader=reader,
    ).module()
    module.register_middlewares(alternative, None)
    module.register_routes(alternative, None)
    client = alternative.test_client()
    _login(client)
    html = client.get('/master-projection').get_data(as_text=True)
    assert 'exclusivamente de lectura' in html
    assert _prepare(client).status_code == 403


def test_csrf_is_required_for_prepare_and_confirm(surface):
    server, _, _, executor = surface
    client = server.test_client()
    _login(client)
    assert _prepare(client, csrf='wrong').status_code == 403
    assert _prepare(client).status_code == 303
    assert _confirm(client, csrf='wrong').status_code == 403
    assert executor.calls == []
    assert _confirm(client).status_code == 303
    assert len(executor.calls) == 1


def test_confirmation_nonce_is_required_and_cannot_be_reused(surface):
    server, _, _, executor = surface
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    assert _confirm(client, nonce='forged-nonce').status_code == 409
    assert executor.calls == []
    token = _field(client.get('/master-projection').get_data(as_text=True), 'csrf')
    assert client.post('/master-projection', data={
        'csrf': token, 'intent': 'confirm', 'nonce': 'forged-nonce',
    }).status_code == 409
    assert executor.calls == []


def test_source_change_during_confirmation_does_not_write(surface):
    server, _, planner, executor = surface
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    prepared = client.get('/master-projection').get_data(as_text=True)
    token = _field(prepared, 'csrf')
    nonce = _field(prepared, 'nonce')
    planner.release = 'release-2'
    attempt = client.post('/master-projection', data={
        'csrf': token, 'intent': 'confirm', 'nonce': nonce,
    })
    assert attempt.status_code == 409
    assert executor.calls == []
    assert 'private' not in attempt.get_data(as_text=True)


def test_blocked_and_unknown_selections_never_write(surface):
    server, _, planner, executor = surface
    client = server.test_client()
    _login(client)
    planner.state = ProjectionPlanState.BLOCKED
    assert 'Preparar despliegue' not in client.get('/master-projection').get_data(as_text=True)
    assert _prepare(client).status_code == 409
    planner.state = ProjectionPlanState.NEVER_PROJECTED
    assert _prepare(client, key='users').status_code == 409
    assert executor.calls == []


def test_material_rotation_revokes_prepared_confirmation(surface):
    server, reader, _, executor = surface
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    prepared = client.get('/master-projection').get_data(as_text=True)
    token, nonce = _field(prepared, 'csrf'), _field(prepared, 'nonce')
    reader.digest = 'b' * 64
    assert client.post('/master-projection', data={
        'csrf': token, 'intent': 'confirm', 'nonce': nonce,
    }).status_code == 403
    assert executor.calls == []
    assert 'Contraseña' in client.get('/master-projection').get_data(as_text=True)


def test_expired_session_cannot_confirm(surface, monkeypatch):
    import ada.web.application.generic.master_projection.web as web

    server, _, _, executor = surface
    now = 100_000
    monkeypatch.setattr(web.time, 'time', lambda: now)
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    prepared = client.get('/master-projection').get_data(as_text=True)
    token, nonce = _field(prepared, 'csrf'), _field(prepared, 'nonce')
    now += 901
    assert client.post('/master-projection', data={
        'csrf': token, 'intent': 'confirm', 'nonce': nonce,
    }).status_code == 403
    assert executor.calls == []


def test_failed_projection_does_not_claim_success_or_expose_private_errors(surface):
    server, _, _, executor = surface
    executor.failure = 'EXECUTION_FAILED'
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    failed = _confirm(client)
    assert failed.status_code == 503
    body = failed.get_data(as_text=True)
    assert 'No fue posible verificar el despliegue' in body
    assert 'private-secret' not in body
    assert 'Proyección aplicada:' not in body
    assert len(executor.calls) == 1


def test_cancel_discards_selection_without_writing(surface):
    server, _, _, executor = surface
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    token = _field(client.get('/master-projection').get_data(as_text=True), 'csrf')
    assert client.post('/master-projection', data={
        'csrf': token, 'intent': 'cancel',
    }).status_code == 303
    page = client.get('/master-projection').get_data(as_text=True)
    assert 'Confirmar despliegue' not in page
    assert executor.calls == []


def test_unknown_action_is_rejected_without_writing(surface):
    server, _, _, executor = surface
    client = server.test_client()
    _login(client)
    token = _field(client.get('/master-projection').get_data(as_text=True), 'csrf')
    assert client.post('/master-projection', data={
        'csrf': token, 'intent': 'users.replace',
    }).status_code == 400
    assert executor.calls == []


def test_unexpected_execution_error_is_controlled_and_does_not_expose_details(surface):
    server, _, _, executor = surface
    executor.failure = 'UNEXPECTED_ERROR'
    client = server.test_client()
    _login(client)
    assert _prepare(client).status_code == 303
    failed = _confirm(client)
    assert failed.status_code == 503
    content = failed.get_data(as_text=True)
    assert 'No fue posible verificar el despliegue' in content
    assert 'private-backend-details' not in content
    assert 'Proyección aplicada:' not in content
    assert len(executor.calls) == 1
