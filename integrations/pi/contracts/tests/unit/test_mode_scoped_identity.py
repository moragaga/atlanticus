import pytest
from atlanticus.integrations.pi.contracts import (
    NotPiiSource,
    PiCatalog,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
    PiWebApiSource,
)


def _tag(
    name: str,
    alias: str,
    mode: PiExtractionMode,
    *,
    active: bool = True,
) -> PiTagDefinition:
    return PiTagDefinition(
        tag_name=name,
        alias=alias,
        value_kind=PiValueKind.FLOAT,
        extraction_mode=mode,
        materializations=(
            (PiMaterialization.LATEST,)
            if mode is PiExtractionMode.INTERPOLATED
            else (PiMaterialization.DAILY,)
        ),
        is_active=active,
    )


@pytest.mark.parametrize('source', [NotPiiSource(), PiWebApiSource(interpolation_seconds=10)])
@pytest.mark.parametrize(
    ('interpolated_name', 'interpolated_alias', 'recorded_name', 'recorded_alias'),
    [
        ('TAG_A', 'shared', 'TAG_A', 'shared'),
        ('TAG_A', 'different', 'TAG_A', 'shared'),
        ('TAG_A', 'shared', 'TAG_B', 'shared'),
    ],
)
def test_catalog_accepts_repeated_names_and_aliases_across_modes(
    source, interpolated_name, interpolated_alias, recorded_name, recorded_alias
) -> None:
    definitions = (
        _tag(interpolated_name, interpolated_alias, PiExtractionMode.INTERPOLATED),
        _tag(recorded_name, recorded_alias, PiExtractionMode.RECORDED),
    )

    assert PiCatalog(source=source, definitions=definitions).definitions == definitions


@pytest.mark.parametrize('mode', list(PiExtractionMode))
@pytest.mark.parametrize('active', [True, False])
def test_catalog_rejects_duplicate_tag_name_within_mode(mode, active) -> None:
    with pytest.raises(ValueError, match='unique tag names'):
        PiCatalog(
            source=NotPiiSource(),
            definitions=(
                _tag('TAG_A', 'alias_a', mode),
                _tag('tag_a', 'alias_b', mode, active=active),
            ),
        )


@pytest.mark.parametrize('mode', list(PiExtractionMode))
@pytest.mark.parametrize('active', [True, False])
def test_catalog_rejects_duplicate_alias_within_mode(mode, active) -> None:
    with pytest.raises(ValueError, match='unique aliases'):
        PiCatalog(
            source=NotPiiSource(),
            definitions=(
                _tag('TAG_A', 'shared', mode),
                _tag('TAG_B', 'shared', mode, active=active),
            ),
        )
