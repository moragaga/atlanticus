from dash.development.base_component import Component

from ada.web.kpis.definition import KpiDefinition, KpiDefinitionConfiguration
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
)

from .helpers import kpi_registry


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


def test_actions_follow_pending_defined_contract() -> None:
    configured = kpi_registry('pending', 'defined')
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='defined', fields={'detail': 'Texto'}),)
    )
    component = build_kpi_definition_editor(
        query_kpi_definitions(configuration, configured, KpiDefinitionQuery()),
        query=KpiDefinitionQuery(),
        kpi_registry=configured,
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
