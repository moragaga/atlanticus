from datetime import UTC, datetime

import pytest

from ada.configuration.kpi_configuration import KpiConfigurationValidationError
from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfiguration,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.configuration.tools_lifecycle import ToolConfigurationProjectionSnapshot
from ada.web.application.configuration_manager.tool_kpi_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)


class ProjectionRepository:
    def __init__(self, value=None):
        self.value = value

    def load(self):
        return self.value

    def save(self, projection):
        self.value = projection
        return projection

    def health_check(self):
        return True


def _sources(tool_key: str):
    return (
        ToolSourceConsumption(
            tool_key=tool_key,
            source_keys=('pi',),
        ),
        ToolSourceOperationalParticipation(
            tool_key=tool_key,
            control_sources=(
                SourceControlPolicy(
                    source_key='pi',
                    pre_degrading_after_seconds=30,
                    degrading_after_seconds=60,
                ),
            ),
        ),
    )


def _projection(structure: ToolStructure) -> ToolConfigurationProjectionSnapshot:
    consumption, participation = _sources(structure.tool_key)
    configuration = ToolConfiguration(
        tool_key=structure.tool_key,
        display_name='Tool',
        kind=structure.kind,
        source_consumption=consumption,
        source_operational_participation=participation,
        structure=structure,
    )
    return ToolConfigurationProjectionSnapshot.create(
        configuration=configuration,
        source_revision='source_r1',
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )


def _process_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='mine_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        components=(
            ToolComponent(
                key='left_context',
                display_name='Contexto',
                layout_role=ProcessLayoutRole.LEFT,
            ),
            ToolComponent(
                key='mine_process',
                display_name='Proceso Mina',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(
                    ToolSubcomponent(
                        key='phase_1',
                        display_name='Fase 1',
                    ),
                    ToolSubcomponent(
                        key='phase_2',
                        display_name='Fase 2',
                    ),
                    ToolSubcomponent(
                        key='phase_3',
                        display_name='Fase 3',
                    ),
                ),
            ),
            ToolComponent(
                key='right_context',
                display_name='Contexto Derecho',
                layout_role=ProcessLayoutRole.RIGHT,
            ),
        ),
    )


def _integrated_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='loading',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='loading_transport',
                        display_name='Carguío y Transporte',
                        linked_component_keys=('transport',),
                    ),
                ),
            ),
            ToolComponent(
                key='transport',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='haulage',
                        display_name='Acarreo',
                    ),
                ),
            ),
        ),
    )


def test_provider_returns_none_without_projected_tool() -> None:
    provider = ToolConfigurationKpiDestinationCatalogProvider(ProjectionRepository())

    assert provider.load() is None


def test_process_catalog_uses_system_and_component_destinations_only() -> None:
    projection = _projection(_process_structure())
    provider = ToolConfigurationKpiDestinationCatalogProvider(ProjectionRepository(projection))

    catalog = provider.load()

    assert catalog is not None
    assert catalog.tool_projection_revision == projection.revision
    assert tuple(destination.key for destination in catalog.destinations) == (
        'global_indicators',
        'time_status',
        'left_context',
        'mine_process',
        'right_context',
    )
    assert 'phase_1' not in catalog.keys
    assert 'phase_2' not in catalog.keys
    assert 'phase_3' not in catalog.keys


def test_process_center_multiple_phase_cards_do_not_create_extra_kpi_destinations() -> None:
    catalog = ToolConfigurationKpiDestinationCatalogProvider(
        ProjectionRepository(_projection(_process_structure()))
    ).load()

    assert catalog is not None
    assert len(catalog.keys) == 5
    assert 'mine_process' in catalog.keys


def test_integrated_linked_subcomponent_is_alarm_visibility_not_kpi_destination() -> None:
    catalog = ToolConfigurationKpiDestinationCatalogProvider(
        ProjectionRepository(_projection(_integrated_structure()))
    ).load()

    assert catalog is not None
    assert tuple(destination.key for destination in catalog.destinations) == (
        'global_indicators',
        'time_status',
        'loading',
        'transport',
    )
    assert 'loading_transport' not in catalog.keys
    assert 'haulage' not in catalog.keys


def test_catalog_preserves_component_display_names_for_manager_presentation() -> None:
    catalog = ToolConfigurationKpiDestinationCatalogProvider(
        ProjectionRepository(_projection(_integrated_structure()))
    ).load()

    assert catalog is not None
    labels = {destination.key: destination.display_name for destination in catalog.destinations}
    assert labels == {
        'global_indicators': 'Global Indicators',
        'time_status': 'Time Status',
        'loading': 'Carguío',
        'transport': 'Transporte',
    }


def test_projected_tool_without_structure_is_invalid_not_absent() -> None:
    consumption, participation = _sources('broken')
    projection = ToolConfigurationProjectionSnapshot.create(
        configuration=ToolConfiguration(
            tool_key='broken',
            display_name='Broken',
            kind=ToolConfigurationKind.PROCESS,
            source_consumption=consumption,
            source_operational_participation=participation,
            structure=None,
        ),
        source_revision='source_r1',
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    provider = ToolConfigurationKpiDestinationCatalogProvider(ProjectionRepository(projection))

    with pytest.raises(
        KpiConfigurationValidationError,
        match='does not contain structure',
    ):
        provider.load()
