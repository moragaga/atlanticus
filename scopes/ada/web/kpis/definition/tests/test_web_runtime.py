from types import SimpleNamespace

import pytest
from dash import Dash

from ada.web.kpis.definition import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.definition.web import (
    KpiDefinitionEditorContext,
    build_kpi_definition_editor_surface,
    create_kpi_definition_editor_module,
    delete_definition,
    save_definition_detail,
)
from ada.web.kpis.definition.web.callbacks import _pattern_action_key
from ada.web.kpis.definition.web.ids import ROW_DELETE_TYPE, ROW_EDIT_TYPE

from .helpers import ProjectionStoreStub, kpi_configuration, kpi_configuration_projection


def context(*keys: str) -> KpiDefinitionEditorContext:
    projection = kpi_configuration_projection(*keys)
    return KpiDefinitionEditorContext(
        kpi_configuration_projection=ProjectionStoreStub(projection),
        kpi_configuration_source_key=projection.source_key,
    )


def test_web_module_registers_definition_callbacks() -> None:
    editor_context = context('availability')
    module = create_kpi_definition_editor_module(editor_context)
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = build_kpi_definition_editor_surface(editor_context)

    assert module.register_callbacks is not None
    module.register_callbacks(app, SimpleNamespace())

    assert len(app.callback_map) >= 4


def test_create_and_edit_detail_preserve_other_fields() -> None:
    configured = kpi_configuration('availability')
    created = save_definition_detail(
        KpiDefinitionConfiguration(),
        configured,
        {'mode': 'create', 'key': 'availability'},
        detail='Disponibilidad',
    )
    imported_future = KpiDefinitionConfiguration(
        (
            KpiDefinition(
                kpi_key='availability',
                fields={'detail': 'Disponibilidad', 'future_field': 'Conservar'},
            ),
        )
    )

    edited = save_definition_detail(
        imported_future,
        configured,
        {'mode': 'edit', 'key': 'availability'},
        detail='Disponibilidad editada',
    )

    assert created.definition('availability').fields['detail'] == 'Disponibilidad'
    assert edited.definition('availability').fields == {
        'detail': 'Disponibilidad editada',
        'future_field': 'Conservar',
    }


def test_definition_creation_requires_configured_kpi_and_detail() -> None:
    configured = kpi_configuration('availability')

    with pytest.raises(ValueError, match='detalle'):
        save_definition_detail(
            KpiDefinitionConfiguration(),
            configured,
            {'mode': 'create', 'key': 'availability'},
            detail=' ',
        )

    with pytest.raises(ValueError, match='ya no está configurado'):
        save_definition_detail(
            KpiDefinitionConfiguration(),
            configured,
            {'mode': 'create', 'key': 'orphan'},
            detail='Texto',
        )


def test_delete_removes_definition_instead_of_disabling_it() -> None:
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='availability', fields={'detail': 'Texto'}),)
    )

    updated = delete_definition(configuration, 'availability')

    assert updated.definitions == ()
    assert updated.definition('availability') is None


def test_pattern_actions_require_positive_real_click() -> None:
    edit = {'type': ROW_EDIT_TYPE, 'key': 'availability'}
    delete = {'type': ROW_DELETE_TYPE, 'key': 'availability'}

    assert _pattern_action_key(edit, ROW_EDIT_TYPE, 0) is None
    assert _pattern_action_key(edit, ROW_EDIT_TYPE, 1) == 'availability'
    assert _pattern_action_key(delete, ROW_DELETE_TYPE, 0) is None
    assert _pattern_action_key(delete, ROW_DELETE_TYPE, 1) == 'availability'
