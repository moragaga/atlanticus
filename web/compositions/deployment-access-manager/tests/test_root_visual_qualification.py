from __future__ import annotations

import re

import pytest

from qualification.runtime import (
    DEMO_LOCK_SECONDS,
    DEMO_PASSWORD,
    DEMO_USER,
    LocalFailureGate,
    build_qualification_runtime,
)


def _csrf(page) -> str:
    match = re.search(r'name="csrf_token" value="([\w-]+)"', page.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def _login(client, password: str):
    token = _csrf(client.get('/manager-root/login'))
    return client.post(
        '/manager-root/login',
        data={'csrf_token': token, 'service_user': DEMO_USER, 'password': password},
    )


def _callback(client, output: str, input_id: str, *, value: int = 1):
    component_id, property_name = output.rsplit('.', 1)
    return client.post(
        '/_dash-update-component',
        json={
            'output': output,
            'outputs': {'id': component_id, 'property': property_name},
            'inputs': [{'id': input_id, 'property': 'n_clicks', 'value': value}],
            'state': [],
            'changedPropIds': [f'{input_id}.n_clicks'],
        },
    )


def test_visual_qualification_login_manager_and_callbacks(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    runtime = build_qualification_runtime(directory=tmp_path)
    client = runtime.web.server.test_client()
    stranger = runtime.web.server.test_client()

    assert client.get('/health/live').status_code == 200
    assert client.get('/manager').status_code == 401
    assert client.get('/_dash-layout').status_code == 401
    assert stranger.get('/manager-root/status').status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 303
    assert client.get('/manager-root/status').status_code == 200
    assert stranger.get('/manager').status_code == 401
    assert client.get('/manager').status_code == 200
    assert client.get('/manager/deployment-access').status_code == 200
    assert client.get('/manager/unknown').status_code == 401
    assert client.get('/api/qualification/private').status_code == 401
    assert client.get('/').status_code == 401

    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert 'atlanticus-manager' in layout.get_data(as_text=True)
    assert 'qualification-private-button' not in layout.get_data(as_text=True)
    dependencies_response = client.get('/_dash-dependencies')
    assert dependencies_response.status_code == 200
    dependencies = dependencies_response.get_json()
    assert isinstance(dependencies, list)
    assert not any(
        item.get('output') == 'qualification-private-output.children' for item in dependencies
    )
    refresh = next(
        item
        for item in dependencies
        if item.get('output', '').endswith('deployment-access-status.children')
    )
    assert len(refresh['inputs']) == 1
    response = _callback(
        client,
        refresh['output'],
        refresh['inputs'][0]['id'],
    )
    assert response.status_code == 200
    assert 'Material ROOT: PRESENT y verificado.' in response.get_data(as_text=True)
    denied = _callback(
        client,
        'qualification-private-output.children',
        'qualification-private-button',
    )
    assert denied.status_code == 401

    runtime.access.create_or_replace(service_user=DEMO_USER, password=DEMO_PASSWORD)
    assert client.get('/manager').status_code == 401
    assert client.get('/manager-root/status').status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 303
    status = client.get('/manager-root/status')
    token = _csrf(status)
    assert client.post('/manager-root/logout', data={'csrf_token': token}).status_code == 303
    assert client.get('/manager').status_code == 401


def test_lockout_after_three_bad_passwords_and_automatic_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    now = [1200.0]
    runtime = build_qualification_runtime(directory=tmp_path, gate_clock=lambda: now[0])
    client = runtime.web.server.test_client()
    different_browser = runtime.web.server.test_client()

    for _ in range(3):
        assert _login(client, 'DemoRoot-incorrect-password').status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 429
    assert _login(different_browser, DEMO_PASSWORD).status_code == 429
    assert client.get('/manager-root/status').status_code == 401
    now[0] += DEMO_LOCK_SECONDS - 1
    assert _login(client, DEMO_PASSWORD).status_code == 429
    now[0] += 1
    assert _login(client, DEMO_PASSWORD).status_code == 303
    assert client.get('/manager').status_code == 200

    assert _login(client, 'DemoRoot-incorrect-password').status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 303
    assert runtime.gate.allow_login_attempt('127.0.0.1') is True


def test_failure_gate_isolated_by_ip_and_success_reset():
    now = [10.0]
    gate = LocalFailureGate(max_failures=2, lock_seconds=5, clock=lambda: now[0])
    assert gate.allow_login_attempt('127.0.0.1')
    gate.record_failure('127.0.0.1')
    gate.record_failure('127.0.0.1')
    assert gate.allow_login_attempt('127.0.0.1') is False
    assert gate.allow_login_attempt('127.0.0.2') is True
    now[0] += 5
    assert gate.allow_login_attempt('127.0.0.1') is True
    gate.record_failure('127.0.0.1')
    gate.record_success('127.0.0.1')
    assert gate.allow_login_attempt('127.0.0.1') is True


def test_visual_qualification_rejects_nonlocal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'production')
    with pytest.raises(ValueError, match='only available in local'):
        build_qualification_runtime(directory=tmp_path)
    assert list(tmp_path.iterdir()) == []
