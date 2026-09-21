from datetime import UTC, datetime

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.tools.catalog import (
    ToolCatalogEntry,
    ToolCatalogSnapshot,
    ToolCatalogStore,
    create_tool_catalog_snapshot,
)
from ada_command_center.web.alarms.configuration import (
    AlarmConfiguration,
    AlarmToolReferenceReader,
)
from atlanticus.web.source.models import SourceReleaseId

from .helpers import message, rule


class _CatalogStore(ToolCatalogStore):
    def __init__(self, snapshot: ToolCatalogSnapshot | None) -> None:
        self.snapshot = snapshot

    def get_current(self) -> ToolCatalogSnapshot | None:
        return self.snapshot

    def replace_current(self, snapshot: ToolCatalogSnapshot) -> ToolCatalogSnapshot:
        self.snapshot = snapshot
        return snapshot


def test_reader_returns_none_when_catalog_does_not_exist() -> None:
    reader = AlarmToolReferenceReader(store=_CatalogStore(None))

    assert reader.load() is None


def test_reader_builds_alarm_reference_catalog_and_preserves_provenance() -> None:
    snapshot = create_tool_catalog_snapshot(
        (_integrated_entry(), _process_entry(), _strategic_entry()),
        generated_at_utc=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
    )

    catalog = AlarmToolReferenceReader(store=_CatalogStore(snapshot)).load()

    assert catalog is not None
    assert catalog.catalog_revision == snapshot.revision
    assert tuple(tool.tool_key for tool in catalog.tools) == (
        'integrated_tool',
        'process_tool',
    )
    integrated = catalog.get_tool('integrated_tool')
    assert integrated is not None
    assert integrated.source_release_id == SourceReleaseId('release-integrated')
    assert tuple(component.component_key for component in integrated.components) == (
        'mine_primary',
        'mine_secondary',
    )


def test_reader_uses_tool_structure_visible_subcomponent_addresses() -> None:
    snapshot = create_tool_catalog_snapshot(
        (_integrated_entry(),),
        generated_at_utc=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
    )
    catalog = AlarmToolReferenceReader(store=_CatalogStore(snapshot)).load()

    assert catalog is not None
    visible = catalog.subcomponents('integrated_tool', 'mine_secondary')
    assert tuple(
        (item.owner_component_key, item.subcomponent_key, item.display_name) for item in visible
    ) == (
        ('mine_secondary', 'haulage', 'Haulage'),
        ('mine_primary', 'crusher', 'Crusher'),
    )


def test_reference_lookup_is_tolerant_for_unknown_keys() -> None:
    snapshot = create_tool_catalog_snapshot(
        (_process_entry(),),
        generated_at_utc=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
    )
    catalog = AlarmToolReferenceReader(store=_CatalogStore(snapshot)).load()

    assert catalog is not None
    assert catalog.get_tool('unknown-tool') is None
    assert catalog.components('unknown-tool') == ()
    assert catalog.subcomponents('process_tool', 'unknown-component') == ()


def test_alarm_configuration_remains_valid_without_catalog_resolution() -> None:
    unresolved = rule(alarm_key='manual-key-alarm')

    configuration = AlarmConfiguration(rules=(unresolved,), messages=(message(),))

    assert configuration.rules[0].escalation.origin_tool_key == 'tool-a'
    assert configuration.rules[0].visual_targets[0].tool_key == 'tool-a'


def _integrated_entry() -> ToolCatalogEntry:
    return ToolCatalogEntry(
        tool_key='integrated_tool',
        display_name='Integrated Tool',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        source_release_id=SourceReleaseId('release-integrated'),
        structure=ToolStructure(
            tool_key='integrated_tool',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine_primary',
                    display_name='Mine Primary',
                    scope=ToolScope.MINE,
                    subcomponents=(
                        ToolSubcomponent(
                            key='crusher',
                            display_name='Crusher',
                            linked_component_keys=('mine_secondary',),
                        ),
                    ),
                ),
                ToolComponent(
                    key='mine_secondary',
                    display_name='Mine Secondary',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='haulage', display_name='Haulage'),),
                ),
            ),
        ),
    )


def _process_entry() -> ToolCatalogEntry:
    return ToolCatalogEntry(
        tool_key='process_tool',
        display_name='Process Tool',
        kind=ToolConfigurationKind.PROCESS,
        source_release_id=SourceReleaseId('release-process'),
        structure=ToolStructure(
            tool_key='process_tool',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(
                ToolComponent(
                    key='plant_process',
                    display_name='Plant Process',
                    subcomponents=(ToolSubcomponent(key='line_a', display_name='Line A'),),
                ),
            ),
        ),
    )


def _strategic_entry() -> ToolCatalogEntry:
    return ToolCatalogEntry(
        tool_key='strategic_tool',
        display_name='Strategic Tool',
        kind=ToolConfigurationKind.STRATEGIC,
        source_release_id=SourceReleaseId('release-strategic'),
        structure=ToolStructure(
            tool_key='strategic_tool',
            kind=ToolConfigurationKind.STRATEGIC,
            components=(ToolComponent(key='strategy', display_name='Strategy'),),
        ),
    )
