import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.tools import (
    ToolDependencyEntry,
    ToolDependencyManifest,
    ToolDependencyManifestValidationError,
)


def _structure(tool_key: str = 'operations') -> ToolStructure:
    return ToolStructure(
        tool_key=tool_key,
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='crusher',
                        display_name='Primary Crusher',
                    ),
                ),
            ),
        ),
    )


def _entry(tool_key: str = 'operations') -> ToolDependencyEntry:
    return ToolDependencyEntry(
        tool_key=tool_key,
        display_name='Integrated Operations',
        source_release_id='tool-release-7',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=_structure(tool_key),
    )


def test_tool_dependency_manifest_round_trips_historical_names_and_structure() -> None:
    value = ToolDependencyManifest(
        confirmed_tool_catalog_revision='catalog-r12',
        tools=(_entry(),),
    )

    restored = ToolDependencyManifest.from_document(value.to_document())

    assert restored == value
    tool = restored.get('operations')
    assert tool is not None
    assert tool.display_name == 'Integrated Operations'
    assert tool.source_release_id == 'tool-release-7'
    assert tool.structure.component('mine').display_name == 'Mine'
    crusher = tool.structure.component('mine').subcomponent('crusher')
    assert crusher.display_name == 'Primary Crusher'


def test_tool_dependency_manifest_exposes_resolver_catalog_protocol() -> None:
    value = ToolDependencyManifest(
        confirmed_tool_catalog_revision='catalog-r12',
        tools=(_entry(),),
    )

    assert value.revision == 'catalog-r12'
    assert value.get('operations') == _entry()
    assert value.get('missing') is None


def test_tool_dependency_manifest_orders_entries_by_tool_key() -> None:
    first = ToolDependencyEntry(
        tool_key='a',
        display_name='A',
        source_release_id='a1',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=_structure('a'),
    )
    second = ToolDependencyEntry(
        tool_key='b',
        display_name='B',
        source_release_id='b1',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        structure=_structure('b'),
    )

    value = ToolDependencyManifest(
        confirmed_tool_catalog_revision='catalog-r12',
        tools=(second, first),
    )

    assert tuple(tool.tool_key for tool in value.tools) == ('a', 'b')


def test_tool_dependency_entry_rejects_structure_identity_mismatch() -> None:
    with pytest.raises(ToolDependencyManifestValidationError):
        ToolDependencyEntry(
            tool_key='operations',
            display_name='Integrated Operations',
            source_release_id='tool-release-7',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            structure=_structure('different_tool'),
        )


def test_tool_dependency_manifest_rejects_duplicate_tool_keys() -> None:
    with pytest.raises(ToolDependencyManifestValidationError):
        ToolDependencyManifest(
            confirmed_tool_catalog_revision='catalog-r12',
            tools=(_entry(), _entry()),
        )
