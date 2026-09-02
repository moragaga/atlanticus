from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule

DEFAULT_ADA_SESSION_RELOAD_AFTER_SECONDS = 7_200
DEFAULT_ADA_SESSION_CHECK_EVERY_SECONDS = 30
ADA_SESSION_RELOAD_AFTER_SECONDS_ENV = 'ADA_SESSION_RELOAD_AFTER_SECONDS'
ADA_SESSION_CHECK_EVERY_SECONDS_ENV = 'ADA_SESSION_CHECK_EVERY_SECONDS'
ADA_SESSION_ASSET_LAYER = AssetLayer(
    name='ada_session',
    load_order=9900,
    package='ada.web.runtime_experience',
    resource_directory='resources/session',
)


@dataclass(frozen=True, slots=True)
class AdaSessionReloadDefinition:
    reload_after_seconds: int = DEFAULT_ADA_SESSION_RELOAD_AFTER_SECONDS
    check_every_seconds: int = DEFAULT_ADA_SESSION_CHECK_EVERY_SECONDS

    def __post_init__(self) -> None:
        _validate_positive_integer('reload_after_seconds', self.reload_after_seconds)
        _validate_positive_integer('check_every_seconds', self.check_every_seconds)
        if self.check_every_seconds > self.reload_after_seconds:
            raise ValueError('check_every_seconds must not exceed reload_after_seconds')


def resolve_ada_session_reload_definition(
    environ: Mapping[str, str] | None = None,
) -> AdaSessionReloadDefinition:
    source = os.environ if environ is None else environ
    return AdaSessionReloadDefinition(
        reload_after_seconds=_read_positive_integer(
            source,
            ADA_SESSION_RELOAD_AFTER_SECONDS_ENV,
            DEFAULT_ADA_SESSION_RELOAD_AFTER_SECONDS,
        ),
        check_every_seconds=_read_positive_integer(
            source,
            ADA_SESSION_CHECK_EVERY_SECONDS_ENV,
            DEFAULT_ADA_SESSION_CHECK_EVERY_SECONDS,
        ),
    )


def create_ada_session_module(
    definition: AdaSessionReloadDefinition | None = None,
) -> WebModule:
    resolved = definition or resolve_ada_session_reload_definition()
    marker = (
        '<div id="ada-session-auto-reload" hidden '
        f'data-reload-after-ms="{resolved.reload_after_seconds * 1000}" '
        f'data-check-every-ms="{resolved.check_every_seconds * 1000}"></div>'
    )
    return WebModule(
        name='ada-session',
        asset_layers=(ADA_SESSION_ASSET_LAYER,),
        index=IndexContribution(body_end_fragments=(marker,)),
    )


def _read_positive_integer(
    environ: Mapping[str, str],
    key: str,
    default: int,
) -> int:
    raw = environ.get(key)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError) as error:
        raise ValueError(f'{key} must be a positive integer') from error
    if value <= 0:
        raise ValueError(f'{key} must be a positive integer')
    return value


def _validate_positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{name} must be a positive integer')
