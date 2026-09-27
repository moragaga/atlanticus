from dataclasses import FrozenInstanceError

import pytest

from ada_command_center.alarms.core import AlarmResolutionKey
from ada_command_center.alarms.materialization import AlarmConfigurationArtifactRef


def _ref(**overrides):
    values = {
        'source_key': 'alarm-configuration',
        'result_id': 'alarm-materialization-' + 'a' * 64,
        'manifest_sha256': 'b' * 64,
        'resolution_key': AlarmResolutionKey('R10', 'C5'),
    }
    values.update(overrides)
    return AlarmConfigurationArtifactRef(**values)


def test_reference_preserves_exact_identity_and_resolution_key():
    reference = _ref()
    assert reference.source_key == 'alarm-configuration'
    assert reference.result_id.endswith('a' * 64)
    assert reference.manifest_sha256 == 'b' * 64
    assert reference.resolution_key.alarm_configuration_revision == 'R10'
    with pytest.raises(FrozenInstanceError):
        reference.manifest_sha256 = 'c' * 64


def test_distinct_evidence_versions_remain_distinct_even_with_shared_revision_key():
    first = _ref()
    second = _ref(result_id='alarm-materialization-' + 'c' * 64)
    assert first.resolution_key == second.resolution_key
    assert first != second


@pytest.mark.parametrize('source_key', ['', ' alarm-configuration', 'alarm-configuration '])
def test_reference_rejects_invalid_source_key(source_key):
    with pytest.raises(ValueError, match='source_key'):
        _ref(source_key=source_key)


@pytest.mark.parametrize('result_id', ['../elsewhere', 'alarm-materialization-abc', 'a' * 64])
def test_reference_rejects_noncanonical_result_id(result_id):
    with pytest.raises(ValueError, match='result_id'):
        _ref(result_id=result_id)


@pytest.mark.parametrize('digest', ['', 'F' * 64, 'f' * 63, 'non-sha'])
def test_reference_rejects_invalid_manifest_digest(digest):
    with pytest.raises(ValueError, match='manifest_sha256'):
        _ref(manifest_sha256=digest)


def test_reference_rejects_non_resolution_key():
    with pytest.raises(TypeError, match='resolution_key'):
        _ref(resolution_key={'alarm_configuration_revision': 'R10'})
