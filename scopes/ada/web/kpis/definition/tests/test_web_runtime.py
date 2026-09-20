import pytest
from ada.web.kpis.definition import KpiDefinition, KpiDefinitionConfiguration
from ada.web.kpis.definition.web import (
    delete_definition,
    save_definition_detail,
)
from .helpers import kpi_registry


def test_create_and_edit_detail_preserve_other_fields() -> None:
    configured = kpi_registry('availability')
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
    configured = kpi_registry('availability')

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


