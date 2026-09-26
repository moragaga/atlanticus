import base64
import json

import pytest

from ada_command_center.web.alarms.configuration.web.import_review import (
    can_confirm,
    inspect_import,
    revision_warning,
)


def _upload(value: object) -> str:
    data = json.dumps(value).encode('utf-8')
    return 'data:application/json;base64,' + base64.b64encode(data).decode('ascii')


def test_simple_configuration_does_not_fabricate_tool_revision():
    preview = inspect_import(_upload({'rules': [], 'messages': []}), 'simple.json')
    assert preview['kind'] == 'Configuración simple'
    assert preview['tool_revision'] is None
    assert can_confirm(preview, None)
    assert revision_warning(preview, None) is not None


def test_snapshot_requires_explicit_revision_and_blocks_mismatch():
    preview = inspect_import(
        _upload(
            {
                'configuration': {'rules': [], 'messages': []},
                'tool_dependencies': {'confirmed_tool_catalog_revision': 'aabb', 'tools': []},
            }
        ),
        'snapshot.json',
    )
    assert preview['tool_revision'] == 'aabb'
    assert can_confirm(preview, 'aabb')
    assert not can_confirm(preview, 'other')
    assert not can_confirm(preview, None)
    assert 'no coincide' in revision_warning(preview, 'other')


@pytest.mark.parametrize(
    'value',
    [
        {'configuration': {'rules': [], 'messages': []}},
        {'configuration': {'rules': [], 'messages': []}, 'tool_dependencies': {}},
        {'rules': {}},
        {'rules': [], 'messages': None},
    ],
)
def test_invalid_import_documents_do_not_produce_review(value):
    with pytest.raises(ValueError):
        inspect_import(_upload(value), 'bad.json')
