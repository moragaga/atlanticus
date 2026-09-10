from __future__ import annotations

from dash.development.base_component import Component

from ada.web.configuration import (
    ConfigurationMutationState,
    ConfigurationMutationStatus,
    ConfigurationPageRequest,
)
from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiDestination,
    KpiDestinationCatalog,
)
from ada.web.kpis.configuration.web import (
    KpiConfigurationQuery,
    build_kpi_configuration_editor,
    build_kpi_configuration_editor_modal,
    query_kpi_configuration,
)


def _prop(component: Component, name: str) -> object:
    return component.to_plotly_json()['props'].get(name)


def _walk(component: object) -> list[Component]:
    found: list[Component] = []
    if isinstance(component, Component):
        found.append(component)
        children = getattr(component, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found.extend(_walk(child))
        elif children is not None:
            found.extend(_walk(children))
    return found


def _catalog() -> KpiDestinationCatalog:
    return KpiDestinationCatalog(
        tool_projection_revision='tool-1',
        destinations=(
            KpiDestination(key='plant', display_name='Plant'),
            KpiDestination(key='crusher', display_name='Crusher'),
        ),
    )


def _configuration() -> KpiConfiguration:
    return KpiConfiguration(
        bindings=tuple(
            KpiConfigurationBinding(
                kpi_key=f'kpi_{index:02d}',
                destination_keys=('plant', 'crusher'),
                latest_enabled=True,
                series_enabled=index % 2 == 0,
                series_hours=12 if index % 2 == 0 else None,
            )
            for index in range(12)
        )
    )


def test_configuration_editor_renders_first_ten_rows_and_pagination() -> None:
    query = KpiConfigurationQuery()
    page = query_kpi_configuration(_configuration(), query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
    )
    nodes = _walk(component)

    edit_actions = [
        node
        for node in nodes
        if isinstance(getattr(node, 'id', None), dict)
        and node.id.get('type') == 'ada-kpi-configuration--row-edit'
    ]
    delete_actions = [
        node
        for node in nodes
        if isinstance(getattr(node, 'id', None), dict)
        and node.id.get('type') == 'ada-kpi-configuration--row-delete'
    ]
    assert len(edit_actions) == 10
    assert len(delete_actions) == 10

    page_size = next(
        node
        for node in nodes
        if getattr(node, 'id', None) == 'ada-kpi-configuration--pagination-page-size'
    )
    assert tuple(option['value'] for option in page_size.options) == (10, 20)


def test_partial_page_keeps_ten_visual_slots() -> None:
    configuration = KpiConfiguration(
        bindings=tuple(
            KpiConfigurationBinding(
                kpi_key=f'kpi_{index:02d}',
                destination_keys=('plant',),
            )
            for index in range(3)
        )
    )
    query = KpiConfigurationQuery()
    page = query_kpi_configuration(configuration, query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
    )

    slots = [
        node
        for node in _walk(component)
        if _prop(node, 'data-row-slot') in {'record', 'empty', 'placeholder'}
    ]
    assert len(slots) == 10
    assert sum(_prop(node, 'data-row-slot') == 'placeholder' for node in slots) == 7


def test_twenty_row_page_keeps_twenty_visual_slots() -> None:
    configuration = KpiConfiguration(
        bindings=tuple(
            KpiConfigurationBinding(
                kpi_key=f'kpi_{index:02d}',
                destination_keys=('plant',),
            )
            for index in range(3)
        )
    )
    query = KpiConfigurationQuery(
        page=ConfigurationPageRequest(page_size=20),
    )
    page = query_kpi_configuration(configuration, query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
    )

    slots = [
        node
        for node in _walk(component)
        if _prop(node, 'data-row-slot') in {'record', 'empty', 'placeholder'}
    ]
    assert len(slots) == 20
    assert sum(_prop(node, 'data-row-slot') == 'placeholder' for node in slots) == 17


def test_empty_configuration_distinguishes_empty_from_filtered() -> None:
    configuration = KpiConfiguration()
    query = KpiConfigurationQuery()
    page = query_kpi_configuration(configuration, query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
    )
    nodes = _walk(component)

    body = next(
        node
        for node in nodes
        if getattr(node, 'id', None) == 'ada-kpi-configuration--table-body'
    )
    assert _prop(body, 'data-empty-reason') == 'empty'

    slots = [
        node
        for node in nodes
        if _prop(node, 'data-row-slot') in {'record', 'empty', 'placeholder'}
    ]
    assert len(slots) == 10
    assert _prop(slots[0], 'data-row-slot') == 'empty'


def test_filtered_empty_configuration_reports_filter_state() -> None:
    configuration = KpiConfiguration(
        bindings=(
            KpiConfigurationBinding(
                kpi_key='availability',
                destination_keys=('plant',),
            ),
        )
    )
    query = KpiConfigurationQuery(search='does-not-exist')
    page = query_kpi_configuration(configuration, query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
    )

    body = next(
        node
        for node in _walk(component)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--table-body'
    )
    assert _prop(body, 'data-empty-reason') == 'filtered'


def test_busy_row_disables_only_its_direct_actions() -> None:
    query = KpiConfigurationQuery()
    page = query_kpi_configuration(_configuration(), query)
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
        query=query,
        mutation=ConfigurationMutationState(
            status=ConfigurationMutationStatus.SAVING,
            item_key='kpi_00',
        ),
    )

    edit_actions = {
        node.id['key']: node
        for node in _walk(component)
        if isinstance(getattr(node, 'id', None), dict)
        and node.id.get('type') == 'ada-kpi-configuration--row-edit'
    }
    delete_actions = {
        node.id['key']: node
        for node in _walk(component)
        if isinstance(getattr(node, 'id', None), dict)
        and node.id.get('type') == 'ada-kpi-configuration--row-delete'
    }

    assert edit_actions['kpi_00'].disabled is True
    assert delete_actions['kpi_00'].disabled is True
    assert edit_actions['kpi_01'].disabled is False
    assert delete_actions['kpi_01'].disabled is False


def test_editor_hours_are_disabled_until_timeseries_is_enabled() -> None:
    modal = build_kpi_configuration_editor_modal(destination_catalog=_catalog())
    hours = next(
        node
        for node in _walk(modal)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--editor-hours'
    )

    assert hours.disabled is True
    hours_field = next(
        node
        for node in _walk(modal)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--editor-hours-field'
    )
    assert hours_field.hidden is True

    title = next(
        node
        for node in _walk(modal)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--editor-title'
    )
    assert title.children == 'Nuevo KPI'

    assert _prop(modal, 'className') == 'ada-kpi-configuration__modal'
    assert any(
        getattr(node, 'id', None) == 'ada-kpi-configuration--editor-backdrop'
        for node in _walk(modal)
    )
    assert any(
        getattr(node, 'id', None) == 'ada-kpi-configuration--editor-close'
        for node in _walk(modal)
    )

def test_modal_uses_latest_row_and_series_hours_row() -> None:
    modal = build_kpi_configuration_editor_modal(destination_catalog=_catalog())
    rows = [
        node
        for node in _walk(modal)
        if 'ada-kpi-configuration__toggle-row'
        in str(getattr(node, 'className', ''))
    ]

    assert len(rows) == 2
    assert 'ada-kpi-configuration__toggle-row--latest' in rows[0].className
    assert 'ada-kpi-configuration__toggle-row--series' in rows[1].className

    hours = next(
        node
        for node in _walk(modal)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--editor-hours-field'
    )
    assert hours.hidden is True


def test_empty_states_are_centered_visual_overlays() -> None:
    empty_page = query_kpi_configuration(KpiConfiguration(), KpiConfigurationQuery())
    empty = build_kpi_configuration_editor(
        empty_page,
        destination_catalog=_catalog(),
    )
    empty_state = next(
        node
        for node in _walk(empty)
        if _prop(node, 'data-empty-state') == 'empty'
    )
    assert 'Todavía no hay KPI configurados.' in str(empty_state.children)

    filtered_query = KpiConfigurationQuery(search='missing')
    filtered_page = query_kpi_configuration(_configuration(), filtered_query)
    filtered = build_kpi_configuration_editor(
        filtered_page,
        destination_catalog=_catalog(),
        query=filtered_query,
    )
    filtered_state = next(
        node
        for node in _walk(filtered)
        if _prop(node, 'data-empty-state') == 'filtered'
    )
    assert 'No se encontraron KPI.' in str(filtered_state.children)


def test_dash_selects_use_atlanticus_configuration_adapter() -> None:
    page = query_kpi_configuration(_configuration(), KpiConfigurationQuery())
    component = build_kpi_configuration_editor(
        page,
        destination_catalog=_catalog(),
    )
    component_filter = next(
        node
        for node in _walk(component)
        if getattr(node, 'id', None) == 'ada-kpi-configuration--destination-filter'
    )
    assert (
        component_filter.style['--Dash-Fill-Interactive-Strong']
        == 'var(--atlanticus-ui-secondary)'
    )
    assert component_filter.labels['search'] == 'Buscar componente'
