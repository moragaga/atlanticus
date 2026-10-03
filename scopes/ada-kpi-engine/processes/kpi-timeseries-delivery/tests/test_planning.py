from __future__ import annotations

from pathlib import Path

import pytest

from ada.kpis.delivery import canonical_revision
from ada.kpis.materialization import (
    KPI_REGISTRY_ITEM_ID,
    LocalKpiRegistryStore,
    materialize_registry,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryReadinessPending,
)
from ada.processes.kpi_timeseries_delivery.planning import (
    build_timeseries_read_plan,
    load_frozen_timeseries_configurations,
)


def _projection(
    *,
    revision: str,
    bindings: list[dict[str, object]],
) -> dict[str, object]:
    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': revision,
        'source_published_at_utc': '2026-10-02T20:00:00Z',
        'projected_at_utc': '2026-10-02T20:00:01Z',
        'dependencies': [
            {
                'source_key': 'tools',
                'source_release_id': 'tools-r1',
                'source_published_at_utc': '2026-10-02T19:00:00Z',
                'dependencies': [],
            }
        ],
        'payload': {'bindings': bindings},
    }


def _binding(
    key: str,
    *,
    hours: int | None,
    series_enabled: bool = True,
) -> dict[str, object]:
    return {
        'kpi_key': key,
        'destination_keys': ['global'],
        'latest_enabled': True,
        'series_enabled': series_enabled,
        'series_hours': hours,
    }


def _store(tmp_path: Path) -> LocalKpiRegistryStore:
    return LocalKpiRegistryStore(root=tmp_path / 'registries')


def test_frozen_configurations_require_exact_materialized_tool_set(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(
            tool_key='tool_a',
            projection=_projection(
                revision='registry-a',
                bindings=[_binding('kpi_a', hours=6)],
            ),
        ),
    )

    with pytest.raises(
        KpiTimeseriesDeliveryReadinessPending,
        match='missing=tool_b',
    ):
        load_frozen_timeseries_configurations(
            store=store,
            expected_tool_keys=('tool_a', 'tool_b'),
        )


def test_frozen_configurations_preserve_registry_identity_and_digest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document = materialize_registry(
        tool_key='tool_a',
        projection=_projection(
            revision='registry-a',
            bindings=[_binding('kpi_a', hours=6)],
        ),
    )
    store.replace(tool_key='tool_a', document=document)

    frozen = load_frozen_timeseries_configurations(
        store=store,
        expected_tool_keys=('tool_a',),
    )

    target = frozen['tool_a']
    assert target.tool_key == 'tool_a'
    assert target.registry_revision == 'registry-a'
    assert target.registry_digest == canonical_revision(document)
    assert target.configuration.tool_projection_revision == 'tools-r1'
    assert target.configuration.bindings[0].key == 'kpi_a'
    assert target.configuration.bindings[0].series_hours == 6


def test_read_plan_unions_enabled_kpis_and_uses_largest_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    documents = {
        'tool_a': materialize_registry(
            tool_key='tool_a',
            projection=_projection(
                revision='registry-a',
                bindings=[
                    _binding('shared', hours=4),
                    _binding('only_a', hours=12),
                    _binding('latest_only', hours=None, series_enabled=False),
                ],
            ),
        ),
        'tool_b': materialize_registry(
            tool_key='tool_b',
            projection=_projection(
                revision='registry-b',
                bindings=[
                    _binding('shared', hours=8),
                    _binding('only_b', hours=24),
                ],
            ),
        ),
    }
    for tool_key, document in documents.items():
        store.replace(tool_key=tool_key, document=document)

    frozen = load_frozen_timeseries_configurations(
        store=store,
        expected_tool_keys=('tool_a', 'tool_b'),
    )
    plan = build_timeseries_read_plan(frozen)

    assert plan.required_columns == ('only_a', 'only_b', 'shared')
    assert plan.max_window_hours == 24


def test_read_plan_can_be_empty_when_no_tool_requests_series(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(
            tool_key='tool_a',
            projection=_projection(
                revision='registry-a',
                bindings=[_binding('latest_only', hours=None, series_enabled=False)],
            ),
        ),
    )

    frozen = load_frozen_timeseries_configurations(
        store=store,
        expected_tool_keys=('tool_a',),
    )
    plan = build_timeseries_read_plan(frozen)

    assert plan.required_columns == ()
    assert plan.max_window_hours == 0
