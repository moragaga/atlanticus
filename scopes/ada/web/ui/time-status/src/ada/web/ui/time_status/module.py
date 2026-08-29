from __future__ import annotations

import re

from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule

from .errors import TimeStatusDefinitionError

_DEFAULT_TIME_ZONE = 'America/Santiago'
_TIME_ZONE_PATTERN = re.compile(r'^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$')

ADA_TIME_STATUS_ASSET_LAYER = AssetLayer(
    name='ada_time_status',
    load_order=150,
    package='ada.web.ui.time_status',
)


def create_ada_time_status_module(*, time_zone: str = _DEFAULT_TIME_ZONE) -> WebModule:
    normalized_time_zone = time_zone.strip()
    if (
        not normalized_time_zone
        or not _TIME_ZONE_PATTERN.fullmatch(normalized_time_zone)
        or any(part in {'.', '..'} for part in normalized_time_zone.split('/'))
    ):
        raise TimeStatusDefinitionError('Time Status time zone has an invalid format')

    return WebModule(
        name='ada-time-status',
        asset_layers=(ADA_TIME_STATUS_ASSET_LAYER,),
        index=IndexContribution(runtime_config={'time_zone': normalized_time_zone}),
    )
