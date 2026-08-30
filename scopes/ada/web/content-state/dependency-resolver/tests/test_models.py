from __future__ import annotations

import pytest

from ada.web.content_state.dependency_resolver import (
    ContentStateDependency,
    ContentStateDependencyError,
)


def test_dependency_normalizes_source_keys_to_tuple() -> None:
    dependency = ContentStateDependency(
        component_key='global_indicators',
        source_keys=['pi'],  # type: ignore[arg-type]
    )

    assert dependency.component_key == 'global_indicators'
    assert dependency.source_keys == ('pi',)


def test_dependency_accepts_multiple_canonical_sources() -> None:
    dependency = ContentStateDependency(
        component_key='operational_panel',
        source_keys=('pi', 'dispatch', 'blockgrade'),
    )

    assert dependency.source_keys == ('pi', 'dispatch', 'blockgrade')


@pytest.mark.parametrize('component_key', ('', 'GlobalIndicators', 'global-indicators', '1global'))
def test_dependency_rejects_invalid_component_key(component_key: str) -> None:
    with pytest.raises(ContentStateDependencyError, match='Invalid Content State component key'):
        ContentStateDependency(component_key=component_key, source_keys=('pi',))


@pytest.mark.parametrize('source_key', ('', 'BlockGrade', 'block-grade', '1source'))
def test_dependency_rejects_invalid_source_key(source_key: str) -> None:
    with pytest.raises(ContentStateDependencyError, match='Invalid Content State source key'):
        ContentStateDependency(component_key='global_indicators', source_keys=(source_key,))


def test_dependency_requires_at_least_one_source() -> None:
    with pytest.raises(ContentStateDependencyError, match='requires source_keys'):
        ContentStateDependency(component_key='global_indicators', source_keys=())


def test_dependency_rejects_duplicate_sources() -> None:
    with pytest.raises(ContentStateDependencyError, match='source_keys must be unique'):
        ContentStateDependency(
            component_key='global_indicators',
            source_keys=('pi', 'pi'),
        )
