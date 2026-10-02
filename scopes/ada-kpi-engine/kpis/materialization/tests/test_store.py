import pytest

from ada.kpis.materialization import (
    KpiMaterializationStoreError,
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from tests.support import projection


def test_store_persists_one_registry_per_tool(tmp_path):
    root = materialization_root(tmp_path.resolve())
    store = LocalKpiRegistryStore(root=root)
    document = materialize_registry(tool_key='tool_a', projection=projection())

    persisted = store.replace(tool_key='tool_a', document=document)

    assert persisted == document
    assert store.read('tool_a') == document
    assert (root / 'tool_a.json').is_file()


def test_store_removes_only_unconfigured_tools(tmp_path):
    store = LocalKpiRegistryStore(root=materialization_root(tmp_path.resolve()))
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(tool_key='tool_a', projection=projection()),
    )
    store.replace(
        tool_key='tool_b',
        document=materialize_registry(tool_key='tool_b', projection=projection(revision='r2')),
    )

    removed = store.remove_unconfigured({'tool_a'})

    assert removed == ('tool_b',)
    assert store.read('tool_a') is not None
    assert store.read('tool_b') is None


def test_store_rejects_symlinked_registry(tmp_path):
    root = materialization_root(tmp_path.resolve())
    store = LocalKpiRegistryStore(root=root)
    store.replace(
        tool_key='tool_a',
        document=materialize_registry(tool_key='tool_a', projection=projection()),
    )
    original = root / 'tool_a.json'
    other = root / 'other.json'
    original.rename(other)
    original.symlink_to(other)

    with pytest.raises(KpiMaterializationStoreError, match='symlink'):
        store.read('tool_a')


def test_materialization_root_is_stable_and_shared(tmp_path):
    assert materialization_root(tmp_path.resolve()) == (
        tmp_path.resolve() / 'ada-kpi-engine/materialization/registries'
    )
