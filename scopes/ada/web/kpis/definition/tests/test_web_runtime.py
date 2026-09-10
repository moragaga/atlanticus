from types import SimpleNamespace

import pytest
from dash import Dash

from ada.web.kpis.definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
)
from ada.web.kpis.definition.web import (
    KpiDefinitionEditorContext,
    build_kpi_definition_editor_surface,
    create_kpi_definition_editor_module,
    delete_definition,
    save_definition_detail,
)
from ada.web.kpis.definition.web.callbacks import _pattern_action_key
from ada.web.kpis.definition.web.ids import ROW_DELETE_TYPE, ROW_EDIT_TYPE


class Authority:
    def __init__(self, *keys: str) -> None:
        self.catalog = KpiDefinitionAuthorityCatalog(
            kpi_configuration_revision='kpi-config-r1',
            kpi_keys=tuple(keys),
        )

    def load(self):
        return self.catalog


def test_web_module_registers_definition_callbacks() -> None:
    context = KpiDefinitionEditorContext(authority=Authority('availability'))
    module = create_kpi_definition_editor_module(context)
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = build_kpi_definition_editor_surface(context)

    assert module.register_callbacks is not None
    module.register_callbacks(app, SimpleNamespace())

    assert len(app.callback_map) >= 4


def test_create_and_edit_detail_preserve_other_fields() -> None:
    authority = Authority('availability').load()
    created = save_definition_detail(
        KpiDefinitionConfiguration(),
        authority,
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
        authority,
        {'mode': 'edit', 'key': 'availability'},
        detail='Disponibilidad editada',
    )

    assert created.definition('availability').fields['detail'] == 'Disponibilidad'
    assert edited.definition('availability').fields == {
        'detail': 'Disponibilidad editada',
        'future_field': 'Conservar',
    }


def test_definition_creation_requires_authoritative_kpi_and_detail() -> None:
    authority = Authority('availability').load()

    with pytest.raises(ValueError, match='detalle'):
        save_definition_detail(
            KpiDefinitionConfiguration(),
            authority,
            {'mode': 'create', 'key': 'availability'},
            detail=' ',
        )

    with pytest.raises(ValueError, match='ya no está configurado'):
        save_definition_detail(
            KpiDefinitionConfiguration(),
            authority,
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
