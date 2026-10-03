import pytest

from atlanticus.datasets import DatasetDefinitionError, SingleArtifactLayout


def test_single_artifact_layout_preserves_legacy_defaults() -> None:
    layout = SingleArtifactLayout()

    assert layout.artifact_name == 'data'
    assert layout.allow_empty is False


def test_single_artifact_layout_accepts_named_empty_artifact() -> None:
    layout = SingleArtifactLayout(artifact_name='current', allow_empty=True)

    assert layout.artifact_name == 'current'
    assert layout.allow_empty is True


@pytest.mark.parametrize('value', ('', '.', '..', '../current', 'nested/current'))
def test_single_artifact_layout_rejects_unsafe_names(value: str) -> None:
    with pytest.raises(DatasetDefinitionError):
        SingleArtifactLayout(artifact_name=value)
