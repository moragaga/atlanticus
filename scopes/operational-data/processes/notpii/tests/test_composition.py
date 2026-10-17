from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.integrations.pi.contracts import (
    NotPiiSource,
    PiCatalog,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
)
from atlanticus.kernel import Environment, OperationStatus
from atlanticus.operational_data.processes.notpii.composition import build_composition


def _catalog() -> PiCatalog:
    return PiCatalog(
        source=NotPiiSource(),
        definitions=(
            PiTagDefinition(
                tag_name='TAG_A',
                alias='tag_a',
                value_kind=PiValueKind.FLOAT,
                extraction_mode=PiExtractionMode.INTERPOLATED,
                materializations=(PiMaterialization.LATEST,),
            ),
        ),
    )


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-notpii',
        'VOLUMEN_PATH': str(tmp_path),
        'POLL_INTERVAL_SECONDS': '3.5',
        'NOTPII_INTERPOLATED_SERVICE_BUS_CONNECTION_STRING': (
            'Endpoint=sb://one/;SharedAccessKeyName=a;SharedAccessKey=b'
        ),
        'NOTPII_INTERPOLATED_SERVICE_BUS_TOPIC_NAME': 'interpolated',
        'NOTPII_INTERPOLATED_SERVICE_BUS_SUBSCRIPTION_NAME': 'materialization',
        'NOTPII_INTERPOLATED_SERVICE_BUS_MAX_WAIT_TIME_SECONDS': '10',
        'NOTPII_RAW_BATCH_SIZE': '100000',
        'NOTPII_MAX_MESSAGE_COUNT': '10',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_passes_notpii_identity_to_data_producer(monkeypatch, tmp_path) -> None:
    import atlanticus.operational_data.processes.notpii.composition as module

    captured = {}
    sentinel = SimpleNamespace(
        receivers={},
        job=SimpleNamespace(run_iteration=lambda context: None),
    )

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(module, 'build_notpii_data_producer', fake_builder)
    composition = build_composition(configuration=_configuration(tmp_path), catalog=_catalog())

    assert composition.definition.poll_interval_seconds == 3.5
    assert composition.producer is sentinel
    assert captured['producer_key'] == 'notpii'
    assert captured['dataset_namespace'] == ('pi', 'not_pii')
    assert captured['max_message_count'] == 10
    assert tuple(captured['service_buses']) == (PiExtractionMode.INTERPOLATED,)


class _Receiver:
    def __init__(self, *, name, events, lease_path, fail_open=False) -> None:
        self.name = name
        self.events = events
        self.lease_path = lease_path
        self.fail_open = fail_open

    def __enter__(self):
        assert self.lease_path.exists()
        self.events.append(f'open:{self.name}')
        if self.fail_open:
            raise RuntimeError('Service Bus receiver could not open')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert self.lease_path.exists()
        self.events.append(f'close:{self.name}')


def test_receiver_lifecycle_is_inside_real_runtime_lease(monkeypatch, tmp_path) -> None:
    import atlanticus.operational_data.processes.notpii.composition as module

    events: list[str] = []
    lease_path = tmp_path / 'operational-data-notpii/.runtime/leases/notpii-materialization.json'
    first = _Receiver(name='interpolated', events=events, lease_path=lease_path)
    second = _Receiver(name='recorded', events=events, lease_path=lease_path)

    def iteration(context):
        context.assert_lease_current()
        assert context.lease_generation == 1
        assert lease_path.exists()
        events.append('iteration')

    producer = SimpleNamespace(
        receivers={'interpolated': first, 'recorded': second},
        job=SimpleNamespace(run_iteration=iteration),
    )
    monkeypatch.setattr(module, 'build_notpii_data_producer', lambda **kwargs: producer)
    composition = build_composition(configuration=_configuration(tmp_path), catalog=_catalog())

    assert events == []
    result = composition.execute(argv=('--run-once',))

    assert result.status is OperationStatus.SUCCESS
    assert result.stop_reason == 'run_once'
    assert events == [
        'open:interpolated', 'open:recorded', 'iteration', 'close:recorded', 'close:interpolated'
    ]
    assert not lease_path.exists()


def test_partial_receiver_open_failure_closes_under_lease(monkeypatch, tmp_path) -> None:
    import atlanticus.operational_data.processes.notpii.composition as module

    events: list[str] = []
    lease_path = tmp_path / 'operational-data-notpii/.runtime/leases/notpii-materialization.json'
    producer = SimpleNamespace(
        receivers={
            'interpolated': _Receiver(name='first', events=events, lease_path=lease_path),
            'recorded': _Receiver(
                name='second', events=events, lease_path=lease_path, fail_open=True
            ),
        },
        job=SimpleNamespace(run_iteration=lambda context: events.append('iteration')),
    )
    monkeypatch.setattr(module, 'build_notpii_data_producer', lambda **kwargs: producer)
    composition = build_composition(configuration=_configuration(tmp_path), catalog=_catalog())

    with pytest.raises(RuntimeError, match='Service Bus receiver could not open'):
        composition.execute(argv=('--run-once',))

    assert events == ['open:first', 'open:second', 'close:first']
    assert not lease_path.exists()
