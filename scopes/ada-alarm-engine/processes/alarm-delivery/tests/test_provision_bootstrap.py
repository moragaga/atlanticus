from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.processes.alarm_delivery import bootstrap


@pytest.mark.parametrize('mode', ('OFF', 'ENSURE'))
def test_provisioning_is_separate_preflight_before_runtime(monkeypatch, tmp_path, mode):
    events = []
    connection = object()
    registry = SimpleNamespace(
        resolve=lambda **kwargs: {'tool_a': connection},
    )
    configuration = SimpleNamespace(values={'APPLICATION': 'delivery'}, environment=object())
    monkeypatch.setattr(bootstrap, 'read_connection_registry', lambda root: registry)
    monkeypatch.setattr(bootstrap, 'load_configuration', lambda **kwargs: configuration)
    monkeypatch.setattr(
        bootstrap.AlarmDeliverySettings,
        'from_configuration',
        lambda value: SimpleNamespace(cosmos_provision_mode=mode),
    )

    def prepare(*, mode, connections):
        assert connections == {'tool_a': connection}
        events.append(('prepare', mode))

    class Composition:
        def execute(self, *, argv):
            events.append(('execute', argv))
            return 'complete'

    monkeypatch.setattr(bootstrap, 'prepare_cosmos_containers', prepare)
    monkeypatch.setattr(bootstrap, 'build_composition', lambda **kwargs: Composition())
    assert bootstrap.run(process_root=tmp_path, argv=['--run-once']) == 'complete'
    assert events == [('prepare', mode), ('execute', ['--run-once'])]


def test_failed_preflight_never_starts_delivery_job(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bootstrap,
        'read_connection_registry',
        lambda root: SimpleNamespace(resolve=lambda **kwargs: {'tool_a': object()}),
    )
    monkeypatch.setattr(
        bootstrap,
        'load_configuration',
        lambda **kwargs: SimpleNamespace(values={}, environment=object()),
    )
    monkeypatch.setattr(
        bootstrap.AlarmDeliverySettings,
        'from_configuration',
        lambda config: SimpleNamespace(cosmos_provision_mode='ENSURE'),
    )

    def fail(**kwargs):
        raise RuntimeError('preflight failure')

    monkeypatch.setattr(bootstrap, 'prepare_cosmos_containers', fail)
    monkeypatch.setattr(
        bootstrap,
        'build_composition',
        lambda **kwargs: pytest.fail('job must not start after preflight failure'),
    )
    with pytest.raises(RuntimeError, match='preflight failure'):
        bootstrap.run(process_root=tmp_path, argv=['--run-once'])
