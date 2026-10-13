from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.application.integrated_operations import create_integrated_operations_extension
from ada.web.application.integrated_operations.modules.dashboard.time_status import (
    DashboardTimeStatusSourceBinding,
    create_dashboard_time_status_detail_provider,
)
from ada.web.operational_render_binding import bind_operational_render
from ada.web.time_status.runtime import TimeStatusRuntimeBinding, build_time_status_runtime_component


def _ok(value: str) -> dict[str, object]:
    return {
        'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
        'value': value, 'parsed_value': value,
    }


def _store(values: dict[str, object], *, tool_key: str = 'operations') -> dict[str, object]:
    return {
        'tool_key': tool_key, 'destination_key': 'time_status',
        'latest': {'manifest': {'revision': 'rev'}, 'values': values},
    }


def _binding():
    return DashboardTimeStatusSourceBinding('blockgrade', 'BlockGrade', 'blockgrade_last_update')


def test_detail_provider_refreshes_from_existing_latest_without_another_callback() -> None:
    provider = create_dashboard_time_status_detail_provider('operations', (_binding(),))
    first = provider.resolve(_store({'blockgrade_last_update': _ok('2026-10-12T21:00:00Z')}))
    second = provider.resolve(_store({'blockgrade_last_update': _ok('2026-10-12T21:00:30Z')}))
    assert first.sources[0].timestamp_iso == '2026-10-12T21:00:00Z'
    assert second.sources[0].timestamp_iso == '2026-10-12T21:00:30Z'
    assert first.sources[0].value == 'Sin información temporal disponible'


@pytest.mark.parametrize('store', [
    None, {}, _store({}), _store({'blockgrade_last_update': _ok('not-a-date')}),
    _store({'blockgrade_last_update': _ok('2026-10-12T21:00:00')}),
    _store({'blockgrade_last_update': {'status': 'ok', 'value_kind': 'value', 'value': '2026-10-12T21:00:00Z'}}),
    _store({'blockgrade_last_update': _ok('2026-10-12T21:00:00Z')}, tool_key='other'),
])
def test_missing_or_invalid_timestamp_has_no_local_date(store: object) -> None:
    provider = create_dashboard_time_status_detail_provider('operations', (_binding(),))
    detail = provider.resolve(store)
    assert detail.sources[0].timestamp_utc is None


def test_provider_integrates_with_single_time_status_runtime() -> None:
    provider = create_dashboard_time_status_detail_provider('operations', (_binding(),))
    runtime_binding = TimeStatusRuntimeBinding(
        consumption=ToolSourceConsumption('operations', ('pi', 'blockgrade')),
        participation=ToolSourceOperationalParticipation(
            'operations',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
            additional_observation_source_keys=('blockgrade',),
        ),
        detail=provider,
    )
    component = build_time_status_runtime_component(
        _store({
            'pi_last_update': _ok('2026-10-12T21:00:00Z'),
            'blockgrade_last_update': _ok('2026-10-12T20:59:00Z'),
        }),
        binding=runtime_binding,
        now_utc=datetime(2026, 10, 12, 21, 0, 10, tzinfo=UTC),
    )
    surface = component.to_plotly_json()['props']['children'][1]
    detail = surface.to_plotly_json()['props']['children']
    rows = detail.to_plotly_json()['props']['children']
    row = next(
        node for node in rows
        if hasattr(node, 'to_plotly_json')
        and node.to_plotly_json()['props'].get('data-source-key') == 'blockgrade'
    )
    value = row.to_plotly_json()['props']['children'][1].to_plotly_json()['props']
    assert value['data-ada-time-status-detail-timestamp-utc'] == '2026-10-12T20:59:00Z'


def test_integrated_operations_extension_owns_detail_binding_without_extra_module() -> None:
    structure = ToolStructure(
        tool_key='operations', kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                'mine', 'Mine', scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent('mine_phase', 'Mine Phase'),),
            ),
            ToolComponent(
                'plant', 'Plant', scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent('float', 'Float'),),
            ),
        ),
    )
    extension = create_integrated_operations_extension(
        bind_operational_render(structure),
        global_indicator_bindings=(),
        time_status_sources=(_binding(),),
    )
    assert extension.time_status_detail is not None
    assert extension.time_status_detail.source_keys == ('blockgrade',)
    assert tuple(module.name for module in extension.modules) == ('ada-integrated-operations-dashboard',)
