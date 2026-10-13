from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.web.ui.time_status import (
    TimeStatusDefinitionError,
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
    build_time_status_detail,
)


def test_additional_timestamp_is_exposed_to_shared_local_time_formatter() -> None:
    state = TimeStatusDetailState((TimeStatusDetailSourceState(
        'blockgrade', 'BlockGrade', 'Sin información temporal disponible',
        timestamp_utc=datetime(2026, 10, 12, 21, 0, tzinfo=UTC),
    ),))
    content = build_time_status_detail(state=state)
    row = content.to_plotly_json()['props']['children'][1]
    value = row.to_plotly_json()['props']['children'][1].to_plotly_json()['props']
    assert value['data-ada-time-status-detail-timestamp-utc'] == '2026-10-12T21:00:00Z'
    assert value['children'] == '----/--/-- --:--:--'


def test_additional_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='timezone-aware'):
        TimeStatusDetailSourceState(
            'blockgrade', 'BlockGrade', 'Sin información',
            timestamp_utc=datetime(2026, 10, 12, 21, 0),
        )
