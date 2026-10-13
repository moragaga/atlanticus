from __future__ import annotations

from ada.web.application.generic import bootstrap
from ada.web.application.generic.settings import AdaGenericSettings


def test_ada_settings_preserve_per_destination_slow_threshold():
    settings = AdaGenericSettings.from_mapping({
        'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
        'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS': '4500',
    })
    assert settings.slow_request_threshold_ms == 4500


def test_ada_composition_explicitly_passes_threshold_to_framework(tmp_path, monkeypatch):
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    settings = AdaGenericSettings.from_mapping({
        'ADA_TOOL_NAMESPACE': 'operaciones_integradas',
        'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS': '4500',
    })
    result = object()
    captured = {}

    def capture(definition, *, external_sink, slow_request_threshold_ms, assets_optimized):
        captured['threshold'] = slow_request_threshold_ms
        captured['external_sink'] = external_sink
        captured['assets_optimized'] = assets_optimized
        return result

    monkeypatch.setattr(bootstrap, 'create_web_application', capture)
    assert bootstrap.create_operational_application_runtime(settings=settings) is result
    assert captured == {
        'threshold': 4500,
        'external_sink': None,
        'assets_optimized': False,
    }
