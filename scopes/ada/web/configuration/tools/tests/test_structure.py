from types import MappingProxyType

import pytest

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfigurationKind,
    ToolConfigurationValidationError,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
    ToolSubcomponentAddress,
)


def _subcomponent(
    key: str,
    *,
    linked_component_keys: tuple[str, ...] = (),
) -> ToolSubcomponent:
    return ToolSubcomponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
        linked_component_keys=linked_component_keys,
    )


def _process_component(
    key: str,
    role: ProcessLayoutRole,
    *,
    subcomponents: tuple[ToolSubcomponent, ...] = (),
) -> ToolComponent:
    return ToolComponent(
        key=key,
        display_name=key.replace('_', ' ').title(),
        layout_role=role,
        subcomponents=subcomponents,
    )


def _process_structure(
    *,
    center_subcomponents: tuple[ToolSubcomponent, ...] = (
        ToolSubcomponent(key='principal', display_name='Principal'),
    ),
) -> ToolStructure:
    return ToolStructure(
        tool_key='mina_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        components=(
            _process_component(
                'mina',
                ProcessLayoutRole.CENTER,
                subcomponents=center_subcomponents,
            ),
        ),
    )


def _integrated_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    _subcomponent('equipos_servicio'),
                    _subcomponent(
                        'gestion_carguio_turno',
                        linked_component_keys=('transporte',),
                    ),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('transporte_global'),),
            ),
            ToolComponent(
                key='molienda',
                display_name='Molienda',
                scope=ToolScope.PLANT,
                subcomponents=(_subcomponent('molienda'),),
            ),
        ),
    )


def test_subcomponent_normalizes_identity_and_links() -> None:
    subcomponent = ToolSubcomponent(
        key=' Gestion ',
        display_name=' Gestión Carguío ',
        linked_component_keys=(' Transporte ',),
    )

    assert subcomponent.key == 'gestion'
    assert subcomponent.display_name == 'Gestión Carguío'
    assert subcomponent.linked_component_keys == ('transporte',)


def test_subcomponent_rejects_duplicate_links() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='linked component keys must be unique',
    ):
        _subcomponent('shared', linked_component_keys=('transporte', 'transporte'))


def test_component_rejects_duplicate_subcomponent_keys() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='duplicate subcomponent keys',
    ):
        ToolComponent(
            key='center',
            display_name='Center',
            subcomponents=(_subcomponent('detail'), _subcomponent('detail')),
        )


def test_process_allows_only_center_component() -> None:
    structure = _process_structure()

    assert structure.component_for_layout_role(ProcessLayoutRole.CENTER).key == 'mina'
    assert structure.alarm_baseline_component_keys == ('mina',)


def test_process_allows_optional_left_right_and_bottom() -> None:
    structure = ToolStructure(
        tool_key='process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            _process_component('left_box', ProcessLayoutRole.LEFT),
            _process_component(
                'center_box',
                ProcessLayoutRole.CENTER,
                subcomponents=(_subcomponent('principal'),),
            ),
            _process_component('right_box', ProcessLayoutRole.RIGHT),
            _process_component('bottom_box', ProcessLayoutRole.BOTTOM),
        ),
    )

    assert tuple(component.layout_role for component in structure.components) == (
        ProcessLayoutRole.LEFT,
        ProcessLayoutRole.CENTER,
        ProcessLayoutRole.RIGHT,
        ProcessLayoutRole.BOTTOM,
    )
    assert structure.alarm_baseline_component_keys == ('center_box',)


def test_process_center_is_expandable_to_multiple_alarm_subcomponents() -> None:
    structure = _process_structure(
        center_subcomponents=(
            _subcomponent('carguio'),
            _subcomponent('transporte'),
            _subcomponent('chancado'),
        )
    )

    assert structure.alarm_subcomponent_addresses == (
        ToolSubcomponentAddress('mina', 'carguio'),
        ToolSubcomponentAddress('mina', 'transporte'),
        ToolSubcomponentAddress('mina', 'chancado'),
    )
    assert structure.alarm_baseline_component_keys == ('mina',)


def test_process_center_can_be_one_single_full_size_alarm_subcomponent() -> None:
    structure = ToolStructure(
        tool_key='flotacion',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            _process_component(
                'flotacion',
                ProcessLayoutRole.CENTER,
                subcomponents=(_subcomponent('flotacion'),),
            ),
        ),
    )

    assert structure.alarm_subcomponent_addresses == (
        ToolSubcomponentAddress('flotacion', 'flotacion'),
    )
    assert structure.alarm_baseline_component_keys == ('flotacion',)


def test_process_non_center_subcomponents_are_not_alarm_targets() -> None:
    structure = ToolStructure(
        tool_key='process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            _process_component(
                'left_box',
                ProcessLayoutRole.LEFT,
                subcomponents=(_subcomponent('left_detail'),),
            ),
            _process_component(
                'center_box',
                ProcessLayoutRole.CENTER,
                subcomponents=(_subcomponent('center_detail'),),
            ),
        ),
    )

    assert structure.alarm_subcomponent_addresses == (
        ToolSubcomponentAddress('center_box', 'center_detail'),
    )
    assert structure.alarm_subcomponent_addresses_for_component('left_box') == ()


def test_process_requires_operational_scope() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='requires operational scope',
    ):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            components=(
                _process_component(
                    'center',
                    ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('principal'),),
                ),
            ),
        )


def test_process_requires_center_role() -> None:
    with pytest.raises(ToolConfigurationValidationError, match='requires CENTER'):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.MINE,
            components=(_process_component('left', ProcessLayoutRole.LEFT),),
        )


def test_process_rejects_duplicate_layout_roles() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='duplicate layout roles',
    ):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.MINE,
            components=(
                _process_component(
                    'center_a',
                    ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('a'),),
                ),
                _process_component(
                    'center_b',
                    ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('b'),),
                ),
            ),
        )


def test_process_requires_at_least_one_center_subcomponent() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='CENTER component requires at least one subcomponent',
    ):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(_process_component('center', ProcessLayoutRole.CENTER),),
        )


def test_process_rejects_component_scope_because_it_inherits_operational_scope() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must not declare scope',
    ):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(
                ToolComponent(
                    key='center',
                    display_name='Center',
                    scope=ToolScope.PLANT,
                    layout_role=ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('principal'),),
                ),
            ),
        )


def test_process_rejects_shared_subcomponents() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must not declare linked component keys',
    ):
        ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(
                _process_component(
                    'center',
                    ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('shared', linked_component_keys=('left',)),),
                ),
                _process_component('left', ProcessLayoutRole.LEFT),
            ),
        )


def test_integrated_operations_accepts_n_components_without_fixed_count() -> None:
    structure = _integrated_structure()

    assert len(structure.components) == 3
    assert structure.alarm_baseline_component_keys == (
        'carguio',
        'transporte',
        'molienda',
    )


def test_integrated_operations_accepts_single_component() -> None:
    structure = ToolStructure(
        tool_key='small_integrated',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='process_a',
                display_name='Process A',
                scope=ToolScope.MINE,
                subcomponents=(_subcomponent('detail'),),
            ),
        ),
    )

    assert structure.alarm_baseline_component_keys == ('process_a',)


def test_integrated_operations_requires_scope_per_component() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='requires scope',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    subcomponents=(_subcomponent('detail'),),
                ),
            ),
        )


def test_integrated_operations_requires_subcomponents_per_component() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='requires subcomponents',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    scope=ToolScope.MINE,
                ),
            ),
        )


def test_integrated_operations_rejects_process_layout_roles() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must not declare Process layout roles',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    scope=ToolScope.MINE,
                    layout_role=ProcessLayoutRole.CENTER,
                    subcomponents=(_subcomponent('detail'),),
                ),
            ),
        )


def test_integrated_operations_rejects_operational_scope() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must not declare operational scope',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            operational_scope=ToolScope.MINE,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('detail'),),
                ),
            ),
        )


def test_shared_subcomponent_is_owned_once_and_visible_from_linked_component() -> None:
    structure = _integrated_structure()

    assert structure.subcomponent_address(
        component_key='carguio',
        subcomponent_key='gestion_carguio_turno',
    ) == ToolSubcomponentAddress('carguio', 'gestion_carguio_turno')
    assert structure.subcomponent_address(
        component_key='transporte',
        subcomponent_key='gestion_carguio_turno',
    ) == ToolSubcomponentAddress('carguio', 'gestion_carguio_turno')
    assert ToolSubcomponentAddress(
        'carguio',
        'gestion_carguio_turno',
    ) in structure.alarm_subcomponent_addresses_for_component('transporte')


def test_shared_subcomponent_does_not_duplicate_global_alarm_identity() -> None:
    structure = _integrated_structure()

    addresses = structure.alarm_subcomponent_addresses

    assert addresses.count(ToolSubcomponentAddress('carguio', 'gestion_carguio_turno')) == 1


def test_shared_subcomponent_rejects_unknown_linked_component() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match="Unknown linked Tool component: 'missing'",
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('shared', linked_component_keys=('missing',)),),
                ),
            ),
        )


def test_shared_subcomponent_rejects_owner_link() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='must not link to its owner component',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='process_a',
                    display_name='Process A',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('shared', linked_component_keys=('process_a',)),),
                ),
            ),
        )


def test_shared_subcomponent_requires_same_scope() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='linked components must share scope',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine_process',
                    display_name='Mine Process',
                    scope=ToolScope.MINE,
                    subcomponents=(
                        _subcomponent(
                            'shared',
                            linked_component_keys=('plant_process',),
                        ),
                    ),
                ),
                ToolComponent(
                    key='plant_process',
                    display_name='Plant Process',
                    scope=ToolScope.PLANT,
                    subcomponents=(_subcomponent('detail'),),
                ),
            ),
        )


def test_visible_subcomponent_namespace_rejects_ambiguous_shared_key() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='ambiguous visible subcomponent key',
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='first',
                    display_name='First',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('shared', linked_component_keys=('second',)),),
                ),
                ToolComponent(
                    key='second',
                    display_name='Second',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('shared'),),
                ),
            ),
        )


def test_kpi_destinations_include_automatic_system_targets_and_components() -> None:
    structure = _integrated_structure()

    assert structure.kpi_destination_keys == (
        'global_indicators',
        'time_status',
        'carguio',
        'transporte',
        'molienda',
    )


def test_structure_rejects_component_key_reserved_for_system_kpi_destination() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match="component key is reserved: 'global_indicators'",
    ):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='global_indicators',
                    display_name='Global Indicators',
                    scope=ToolScope.MINE,
                    subcomponents=(_subcomponent('detail'),),
                ),
            ),
        )


def test_document_roundtrip_preserves_shared_topology() -> None:
    structure = _integrated_structure()

    restored = ToolStructure.from_document(MappingProxyType(structure.to_document()))

    assert restored == structure


def test_structure_document_contains_topology_not_rendering_details() -> None:
    document = _process_structure().to_document()

    assert tuple(document) == (
        'tool_key',
        'kind',
        'operational_scope',
        'components',
    )
    serialized = repr(document).casefold()
    for forbidden in (
        'renderer',
        'css',
        'width',
        'store_id',
        'callback',
        'alarm_points',
    ):
        assert forbidden not in serialized
