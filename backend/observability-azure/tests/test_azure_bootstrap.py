from __future__ import annotations

import json
import traceback
from datetime import UTC, date, datetime

import pytest

from atlanticus.kernel import DataSanitizer
from atlanticus.observability import (
    ErrorInfo,
    EventAudience,
    EventCategory,
    EventSeverity,
    ExecutionContext,
    ObservabilityEvent,
    ObservabilitySettings,
    SpanError,
)
from atlanticus.observability_azure import (
    AzureObservabilityBootstrapError,
    AzurePreviewWriter,
    build_azure_observability_extension,
)


class _Backend:
    def __init__(self) -> None:
        self.records = []
        self.closed = False

    def emit(self, payload, severity) -> None:
        self.records.append((payload, severity))

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path) -> ObservabilitySettings:
    return ObservabilitySettings.build(
        application='ada',
        service='dispatch-job',
        module='dispatch',
        environment='dev',
        volume_path=tmp_path,
    )


def _day_directory(tmp_path):
    day = datetime.now(UTC).date().isoformat()
    return tmp_path / 'ada' / 'logs' / 'dispatch-job' / f'day={day}'


def test_preview_profiles_keep_the_same_operational_payload_and_drop_noise(tmp_path) -> None:
    records = []
    event = ObservabilityEvent(
        name='data.downloaded',
        category=EventCategory.DATA,
        audience=EventAudience.OPERATIONS,
        severity=EventSeverity.INFO,
        metrics={'record_count': 10},
    )

    for profile in ('slim', 'diagnostic'):
        profile_path = tmp_path / profile
        settings = _settings(profile_path)
        extension = build_azure_observability_extension(
            observability_settings=settings,
            environ={
                'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
                'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': profile,
            },
        )
        extension.sink.emit(
            ObservabilityEvent(name='dependency.started', category=EventCategory.DEPENDENCY),
            settings,
            DataSanitizer(),
        )
        extension.sink.emit(event, settings, DataSanitizer())

        path = _day_directory(profile_path) / 'azure-preview.jsonl'
        profile_records = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(profile_records) == 1
        records.append(profile_records[0])

    assert records[0] == records[1]
    assert records[0]['event'] == 'data.downloaded'
    assert records[0]['application'] == 'ada'
    assert records[0]['record_count'] == 10


def test_export_sink_uses_safe_compact_payload_and_closes_backend(tmp_path) -> None:
    backend = _Backend()
    settings = _settings(tmp_path)
    extension = build_azure_observability_extension(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
            'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=fake',
        },
        backend_factory=lambda azure, local: backend,
    )
    event = ObservabilityEvent(
        name='alarm.evaluation.failed',
        category=EventCategory.DATA,
        severity=EventSeverity.ERROR,
        metrics={'alarms_failed': 2},
        error=ErrorInfo.from_exception(RuntimeError('secret-value')),
    )

    extension.sink.emit(event, settings, DataSanitizer())
    extension.sink.close()

    payload, severity = backend.records[0]
    assert payload['event'] == 'alarm.evaluation.failed'
    assert payload['application'] == 'ada'
    assert payload['alarms_failed'] == 2
    assert payload['error_type'] == 'RuntimeError'
    assert payload['error_message'] == 'RuntimeError raised'
    assert 'secret-value' not in json.dumps(payload)
    assert severity is EventSeverity.ERROR
    assert backend.closed


def test_backend_factory_contract_is_validated_and_error_is_safe(tmp_path) -> None:
    secret = 'InstrumentationKey=must-not-leak'

    with pytest.raises(AzureObservabilityBootstrapError) as captured:
        build_azure_observability_extension(
            observability_settings=_settings(tmp_path),
            environ={
                'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
                'APPLICATION_INSIGHTS_CONNECTION_STRING': secret,
            },
            backend_factory=lambda azure, local: object(),
        )

    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert secret not in ''.join(traceback.format_exception(captured.value))


def test_partial_backend_is_closed_without_masking_bootstrap_error(tmp_path, monkeypatch) -> None:
    backend = _Backend()

    class _FailingTraceBridge:
        def __init__(self, **kwargs):
            raise RuntimeError('InstrumentationKey=must-not-leak')

    monkeypatch.setattr(
        'atlanticus.observability_azure.bootstrap.AzureMonitorTraceBridge',
        _FailingTraceBridge,
    )

    with pytest.raises(AzureObservabilityBootstrapError, match='bootstrap failed') as captured:
        build_azure_observability_extension(
            observability_settings=_settings(tmp_path),
            environ={
                'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
                'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
                'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=fake',
            },
            backend_factory=lambda azure, local: backend,
        )

    assert backend.closed
    assert 'must-not-leak' not in str(captured.value)
    assert 'must-not-leak' not in ''.join(traceback.format_exception(captured.value))


def test_diagnostic_preview_persists_failed_span_snapshot_once(tmp_path) -> None:
    settings = _settings(tmp_path)
    extension = build_azure_observability_extension(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
        },
    )
    attributes = {
        'component': 'atlanticus.connectivity.blob',
        'source': 'x' * 300,
        'credential_scope': 'must-not-be-persisted',
    }
    handle = extension.trace_bridge.start_span(
        'blob.download',
        context=ExecutionContext(
            application='fake-application',
            environment='prd',
            service='fake-service',
            run_id='run-1',
            iteration=2,
        ),
        attributes=attributes,
    )
    attributes['component'] = 'mutated'
    handle.end(SpanError(error_type='TimeoutError', message='TimeoutError raised'))
    handle.end(SpanError(error_type='RuntimeError', message='RuntimeError raised'))

    records = [
        json.loads(line)
        for line in (_day_directory(tmp_path) / 'azure-diagnostic-spans.jsonl')
        .read_text()
        .splitlines()
    ]
    assert len(records) == 1
    span = records[0]
    assert span['application'] == 'ada'
    assert span['environment'] == 'dev'
    assert span['service'] == 'dispatch-job'
    assert span['run_id'] == 'run-1'
    assert span['iteration'] == 2
    assert span['span'] == 'blob.download'
    assert span['component'] == 'atlanticus.connectivity.blob'
    assert len(span['source']) == 256
    assert span['source'].endswith('…')
    assert span['status'] == 'error'
    assert span['error_type'] == 'TimeoutError'
    assert 'credential_scope' not in span


def test_diagnostic_preview_drops_fast_span_and_keeps_slow_span(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    extension = build_azure_observability_extension(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
        },
    )
    ticks = iter((10.0, 10.1, 20.0, 22.5))
    monkeypatch.setattr(
        'atlanticus.observability_azure.tracing.time.monotonic',
        lambda: next(ticks),
    )
    context = ExecutionContext(
        application='ada',
        environment='dev',
        service='dispatch-job',
        run_id='run-1',
    )

    extension.trace_bridge.start_span(
        'dependency.fast',
        context=context,
        attributes={'component': 'test'},
    ).end()
    assert not (_day_directory(tmp_path) / 'azure-diagnostic-spans.jsonl').exists()

    extension.trace_bridge.start_span(
        'dependency.slow',
        context=context,
        attributes={'component': 'test'},
    ).end()

    span = json.loads(
        (_day_directory(tmp_path) / 'azure-diagnostic-spans.jsonl').read_text().splitlines()[0]
    )
    assert span['span'] == 'dependency.slow'
    assert span['status'] == 'slow'
    assert span['duration_ms'] == 2500.0


def test_preview_bootstrap_suppresses_sensitive_exception_context(tmp_path, monkeypatch) -> None:
    class _FailingPreviewWriter:
        def __init__(self, volume_path):
            raise RuntimeError('InstrumentationKey=must-not-leak')

    monkeypatch.setattr(
        'atlanticus.observability_azure.bootstrap.AzurePreviewWriter',
        _FailingPreviewWriter,
    )

    with pytest.raises(AzureObservabilityBootstrapError) as captured:
        build_azure_observability_extension(
            observability_settings=_settings(tmp_path),
            environ={'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview'},
        )

    assert 'must-not-leak' not in ''.join(traceback.format_exception(captured.value))


@pytest.mark.parametrize(
    'file_name', ['../escape.jsonl', 'nested/file.jsonl', 'nested\\file.jsonl', '.', '..']
)
def test_preview_writer_rejects_non_basename_file_names(tmp_path, file_name) -> None:
    writer = AzurePreviewWriter(tmp_path)

    with pytest.raises(ValueError, match='basename'):
        writer.append(
            {'event': 'test'},
            settings=_settings(tmp_path),
            event_day=date.today(),
            file_name=file_name,
        )
