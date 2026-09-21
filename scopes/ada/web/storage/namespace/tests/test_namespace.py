from pathlib import Path

import pytest

from ada.web.storage.namespace import AdaStorageNamespace


def test_namespace_derives_global_and_tool_prefixes() -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='operaciones_integradas',
    )

    assert namespace.application_prefix == 'conciencia_situacional'
    assert namespace.tool_prefix == 'conciencia_situacional/operaciones_integradas'


def test_namespace_derives_local_application_tool_and_projection_roots() -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='mina',
    )

    assert namespace.local_application_root('/data') == Path('/data/conciencia_situacional')
    assert namespace.local_tool_root('/data') == Path('/data/conciencia_situacional/mina')
    assert namespace.local_projection_root('/data') == Path(
        '/data/conciencia_situacional/mina/projections'
    )


def test_namespace_keeps_global_and_tool_blob_paths_independent() -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='chancado',
    )

    assert (
        namespace.application_blob_name('users/users.json.gz')
        == 'conciencia_situacional/users/users.json.gz'
    )
    assert (
        namespace.tool_blob_name('runtime/checkpoint.json')
        == 'conciencia_situacional/chancado/runtime/checkpoint.json'
    )


def test_source_store_root_stops_at_tool_namespace() -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='flotacion_selectiva',
    )

    assert namespace.local_tool_root('/data') == Path(
        '/data/conciencia_situacional/flotacion_selectiva'
    )
    assert namespace.tool_prefix == 'conciencia_situacional/flotacion_selectiva'
    assert 'sources' not in namespace.tool_prefix


@pytest.mark.parametrize(
    'field,value',
    [
        ('application_namespace', ''),
        ('application_namespace', ' conciencia_situacional'),
        ('application_namespace', 'conciencia/situacional'),
        ('tool_namespace', ''),
        ('tool_namespace', '..'),
        ('tool_namespace', 'mina/chancado'),
    ],
)
def test_namespace_rejects_invalid_segments(field: str, value: str) -> None:
    values = {
        'application_namespace': 'conciencia_situacional',
        'tool_namespace': 'mina',
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError)):
        AdaStorageNamespace(**values)


def test_local_roots_require_absolute_base_path() -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='mina',
    )

    with pytest.raises(ValueError, match='absolute'):
        namespace.local_tool_root('relative-data')


@pytest.mark.parametrize(
    'relative_path',
    ('', '/users/users.json.gz', '../users/users.json.gz', 'users/../users.json.gz'),
)
def test_blob_paths_reject_unsafe_relative_paths(relative_path: str) -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='mina',
    )

    with pytest.raises(ValueError, match='safe relative path'):
        namespace.application_blob_name(relative_path)
