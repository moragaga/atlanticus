from __future__ import annotations

from pathlib import Path

import pytest

from ada.web.runtime_experience import (
    ADA_SESSION_ASSET_LAYER,
    ADA_SESSION_CHECK_EVERY_SECONDS_ENV,
    ADA_SESSION_RELOAD_AFTER_SECONDS_ENV,
    DEFAULT_ADA_SESSION_CHECK_EVERY_SECONDS,
    DEFAULT_ADA_SESSION_RELOAD_AFTER_SECONDS,
    AdaSessionReloadDefinition,
    create_ada_session_module,
    resolve_ada_session_reload_definition,
)


def test_session_reload_definition_defaults_to_two_hours() -> None:
    definition = resolve_ada_session_reload_definition({})

    assert definition == AdaSessionReloadDefinition(
        reload_after_seconds=DEFAULT_ADA_SESSION_RELOAD_AFTER_SECONDS,
        check_every_seconds=DEFAULT_ADA_SESSION_CHECK_EVERY_SECONDS,
    )
    assert definition.reload_after_seconds == 7_200
    assert definition.check_every_seconds == 30


def test_session_reload_definition_accepts_ada_specific_configuration() -> None:
    definition = resolve_ada_session_reload_definition(
        {
            ADA_SESSION_RELOAD_AFTER_SECONDS_ENV: '3600',
            ADA_SESSION_CHECK_EVERY_SECONDS_ENV: '15',
        }
    )

    assert definition == AdaSessionReloadDefinition(
        reload_after_seconds=3_600,
        check_every_seconds=15,
    )


@pytest.mark.parametrize(
    ('environ', 'message'),
    (
        ({ADA_SESSION_RELOAD_AFTER_SECONDS_ENV: '0'}, 'must be a positive integer'),
        ({ADA_SESSION_RELOAD_AFTER_SECONDS_ENV: 'abc'}, 'must be a positive integer'),
        (
            {
                ADA_SESSION_RELOAD_AFTER_SECONDS_ENV: '30',
                ADA_SESSION_CHECK_EVERY_SECONDS_ENV: '31',
            },
            'must not exceed',
        ),
    ),
)
def test_session_reload_definition_rejects_invalid_configuration(
    environ: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_ada_session_reload_definition(environ)


def test_session_module_publishes_stable_marker_and_extracted_asset() -> None:
    module = create_ada_session_module(
        AdaSessionReloadDefinition(
            reload_after_seconds=120,
            check_every_seconds=10,
        )
    )

    assert module.name == 'ada-session'
    assert module.asset_layers == (ADA_SESSION_ASSET_LAYER,)
    assert ADA_SESSION_ASSET_LAYER.package == 'ada.web.runtime_experience'
    assert module.index.body_end_fragments == (
        '<div id="ada-session-auto-reload" hidden '
        'data-reload-after-ms="120000" data-check-every-ms="10000"></div>',
    )


def test_session_javascript_has_no_tool_specific_contract() -> None:
    source = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'runtime_experience'
        / 'resources'
        / 'session'
        / 'js'
        / '10-session-auto-reload.js'
    ).read_text(encoding='utf-8')

    assert "const OPERATIONAL_PATH = '/';" in source
    assert 'window.location.pathname === OPERATIONAL_PATH' in source
    assert "document.visibilityState !== 'visible'" in source
    assert "document.addEventListener('visibilitychange'" in source
    assert 'localStorage' not in source
    assert 'sessionStorage' not in source
    assert 'serviceWorker' not in source
    assert 'integrated_operations' not in source.lower()
    assert 'flotacion' not in source.lower()
    assert 'carguio' not in source.lower()
