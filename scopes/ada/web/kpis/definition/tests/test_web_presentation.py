from dash.development.base_component import Component

from ada.web.kpis.definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
)
from ada.web.kpis.definition.web import (
    KpiDefinitionQuery,
    build_kpi_definition_detail_view,
    build_kpi_definition_editor,
    query_kpi_definitions,
)
from ada.web.kpis.definition.web.ids import (
    ROW_ADD_TYPE,
    ROW_DELETE_TYPE,
    ROW_EDIT_TYPE,
    ROW_VIEW_TYPE,
    TABLE_BODY_ID,
)


def _authority(*keys: str) -> KpiDefinitionAuthorityCatalog:
    return KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision='kpi-config-r1',
        kpi_keys=tuple(keys),
    )


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


def test_grid_contains_only_kpi_status_and_actions_columns() -> None:
    authority = _authority('pending', 'defined')
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='defined', fields={'detail': 'Texto'}),)
    )
    page = query_kpi_definitions(configuration, authority, KpiDefinitionQuery())
    component = build_kpi_definition_editor(
        page,
        query=KpiDefinitionQuery(),
        authority=authority,
    )

    headers = [
        node.children
        for node in _walk(component)
        if node.__class__.__name__ == 'Th'
    ]

    assert headers == ['KPI', 'Estado', 'Acciones']
    assert 'Detalle' not in headers


def test_actions_follow_pending_defined_contract() -> None:
    authority = _authority('pending', 'defined')
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='defined', fields={'detail': 'Texto'}),)
    )
    component = build_kpi_definition_editor(
        query_kpi_definitions(configuration, authority, KpiDefinitionQuery()),
        query=KpiDefinitionQuery(),
        authority=authority,
    )

    pattern_types = [
        node.id.get('type')
        for node in _walk(component)
        if isinstance(getattr(node, 'id', None), dict)
    ]

    assert ROW_ADD_TYPE in pattern_types
    assert ROW_VIEW_TYPE in pattern_types
    assert ROW_EDIT_TYPE in pattern_types
    assert ROW_DELETE_TYPE in pattern_types


def test_grid_keeps_ten_logical_slots_on_desktop() -> None:
    authority = _authority('only')
    component = build_kpi_definition_editor(
        query_kpi_definitions(
            KpiDefinitionConfiguration(),
            authority,
            KpiDefinitionQuery(),
        ),
        query=KpiDefinitionQuery(),
        authority=authority,
    )
    tbody = next(
        node for node in _walk(component) if getattr(node, 'id', None) == TABLE_BODY_ID
    )

    assert len(tbody.children) == 10
    assert tbody.to_plotly_json()['props']['data-page-size'] == '10'


def test_detail_view_renders_all_current_and_future_fields() -> None:
    definition = KpiDefinition(
        kpi_key='availability',
        fields={
            'detail': 'Disponibilidad operacional',
            'unit': '%',
            'owner': 'Operaciones',
        },
    )
    view = build_kpi_definition_detail_view(definition)
    text = ' '.join(
        str(node.children)
        for node in _walk(view)
        if isinstance(getattr(node, 'children', None), str)
    )

    assert 'Disponibilidad operacional' in text
    assert '%' in text
    assert 'Operaciones' in text


def test_no_global_add_definition_control_is_rendered() -> None:
    authority = _authority('pending')
    component = build_kpi_definition_editor(
        query_kpi_definitions(
            KpiDefinitionConfiguration(),
            authority,
            KpiDefinitionQuery(),
        ),
        query=KpiDefinitionQuery(),
        authority=authority,
    )
    string_ids = {
        node.id
        for node in _walk(component)
        if isinstance(getattr(node, 'id', None), str)
    }

    assert 'ada-kpi-definition--add' not in string_ids
