from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from flask import Flask

from ada.web.application.generic.master_projection.web import (
    MASTER_PROJECTION_ROUTE,
    MasterProjectionWebBinding,
)


class MaterialReader:
    def __init__(self) -> None:
        self.status = 'PRESENT'
        self.digest = 'a' * 64
        self.calls = 0

    def inspect(self) -> str:
        return self.status

    def fingerprint(self) -> str | None:
        return self.digest

    def unlock(self, *, service_user, password, application_namespace, environment):
        self.calls += 1
        if service_user != 'master-service' or password != 'a-long-correct-password':
            raise ValueError('Invalid credentials')
        return SimpleNamespace(
            material_id='material-1',
            service_user=service_user,
            application_namespace=application_namespace,
            environment=environment,
            allowed_actions=('projection.preview', 'projection.apply', 'users.replace'),
        )


class Planner:
    def __init__(self) -> None:
        self.calls = 0

    def inspect(self):
        self.calls += 1
        return SimpleNamespace(
            entries=(
                SimpleNamespace(
                    key=SimpleNamespace(value='profiles-configuration'),
                    state=SimpleNamespace(value='SOURCE_MISSING'),
                    prerequisites=(),
                    blocked_by=(),
                ),
            ),
            users=SimpleNamespace(
                state=SimpleNamespace(value='SNAPSHOT_SELECTION_REQUIRED'),
                snapshot_ids=('<script>alert(1)</script>',),
            ),
        )


@pytest.fixture
def surface(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    reader = MaterialReader()
    planner = Planner()
    server = Flask(__name__)
    server.testing = True
    module = MasterProjectionWebBinding(
        application_namespace='conciencia_situacional',
        environment='local',
        reader=reader,
        planner=planner,
    ).module()
    module.register_middlewares(server, None)
    module.register_routes(server, None)
    return server, reader, planner


def _csrf(page: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', page)
    assert match
    return match[1]


def _login(client, password='a-long-correct-password', user='master-service'):
    token = _csrf(client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True))
    return client.post(
        MASTER_PROJECTION_ROUTE,
        data={
            'csrf': token,
            'service_user': user,
            'password': password,
        },
    )


def test_absent_material_returns_controlled_page_without_login(surface):
    server, reader, planner = surface
    reader.status = 'ABSENT'
    response = server.test_client().get(MASTER_PROJECTION_ROUTE)
    assert response.status_code == 200
    assert 'No existe acceso Master Projection configurado' in response.get_data(as_text=True)
    assert '<form method="post" action="/master-projection"' not in response.get_data(as_text=True)
    assert planner.calls == 0


def test_invalid_material_does_not_show_login(surface):
    server, reader, planner = surface
    reader.status = 'INVALID'
    response = server.test_client().get(MASTER_PROJECTION_ROUTE)
    assert response.status_code == 503
    assert 'material de acceso Master Projection es inválido' in response.get_data(as_text=True)
    assert planner.calls == 0


def test_unauthenticated_operator_cannot_inspect_plan(surface):
    server, _, planner = surface
    page = server.test_client().get(MASTER_PROJECTION_ROUTE)
    assert page.status_code == 200
    assert 'Contraseña' in page.get_data(as_text=True)
    assert 'profiles-configuration' not in page.get_data(as_text=True)
    assert planner.calls == 0


def test_login_displays_read_only_plan_and_escapes_snapshot_ids(surface):
    server, _, planner = surface
    client = server.test_client()
    login = _login(client)
    assert login.status_code == 303
    page = client.get(MASTER_PROJECTION_ROUTE)
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'exclusivamente de lectura' in body
    assert 'profiles-configuration' in body
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body
    assert planner.calls == 1
    assert page.headers['Cache-Control'] == 'no-store, private'
    assert 'frame-ancestors' in page.headers['Content-Security-Policy']


def test_invalid_login_never_inspects_plan(surface):
    server, reader, planner = surface
    client = server.test_client()
    response = _login(client, password='incorrect-but-long')
    assert response.status_code == 200
    assert 'Credenciales incorrectas' in response.get_data(as_text=True)
    assert reader.calls == 1
    assert planner.calls == 0


def test_csrf_is_required_before_unlock(surface):
    server, reader, planner = surface
    client = server.test_client()
    response = client.post(
        MASTER_PROJECTION_ROUTE,
        data={
            'csrf': 'arbitrary',
            'service_user': 'master-service',
            'password': 'a-long-correct-password',
        },
    )
    assert response.status_code == 403
    assert reader.calls == planner.calls == 0


def test_material_replacement_revokes_existing_session(surface):
    server, reader, planner = surface
    client = server.test_client()
    assert _login(client).status_code == 303
    reader.digest = 'b' * 64
    page = client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True)
    assert 'Contraseña' in page
    assert planner.calls == 0


def test_removed_material_revokes_existing_session(surface):
    server, reader, planner = surface
    client = server.test_client()
    assert _login(client).status_code == 303
    reader.status = 'ABSENT'
    page = client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True)
    assert 'No existe acceso' in page
    assert planner.calls == 0


def test_session_expires_without_sliding_extension(surface, monkeypatch):
    server, _, planner = surface
    import ada.web.application.generic.master_projection.web as web

    now = 100_000
    monkeypatch.setattr(web.time, 'time', lambda: now)
    client = server.test_client()
    assert _login(client).status_code == 303
    now += 901
    body = client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True)
    assert 'Contraseña' in body
    assert planner.calls == 0


def test_logout_is_post_and_requires_csrf(surface):
    server, _, planner = surface
    client = server.test_client()
    assert _login(client).status_code == 303
    assert client.get('/master-projection/logout').status_code == 405
    assert client.post('/master-projection/logout', data={'csrf': 'wrong'}).status_code == 403
    token = _csrf(client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True))
    assert client.post('/master-projection/logout', data={'csrf': token}).status_code == 303
    assert 'Contraseña' in client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True)
    assert planner.calls == 1


def test_oversized_login_is_rejected_without_unlock(surface):
    server, reader, planner = surface
    client = server.test_client()
    token = _csrf(client.get(MASTER_PROJECTION_ROUTE).get_data(as_text=True))
    response = client.post(
        MASTER_PROJECTION_ROUTE,
        data={
            'csrf': token,
            'service_user': 'a' * 5000,
            'password': 'a-long-correct-password',
        },
    )
    assert response.status_code == 413
    assert reader.calls == planner.calls == 0


def test_unconfigured_reader_is_absent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    server = Flask(__name__)
    module = MasterProjectionWebBinding('app', 'local', None).module()
    module.register_middlewares(server, None)
    module.register_routes(server, None)
    assert 'No existe acceso' in server.test_client().get(MASTER_PROJECTION_ROUTE).get_data(
        as_text=True
    )
