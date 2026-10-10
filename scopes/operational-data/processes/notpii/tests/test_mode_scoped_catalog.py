import atlanticus.operational_data.processes.notpii.catalog.provider as provider
from atlanticus.integrations.pi.contracts import (
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
)


def test_catalog_accepts_shared_name_and_alias_in_both_modes(monkeypatch) -> None:
    definitions = (
        PiTagDefinition(
            tag_name='TAG_A',
            alias='shared',
            value_kind=PiValueKind.FLOAT,
            extraction_mode=PiExtractionMode.INTERPOLATED,
            materializations=(PiMaterialization.LATEST,),
        ),
        PiTagDefinition(
            tag_name='TAG_A',
            alias='shared',
            value_kind=PiValueKind.FLOAT,
            extraction_mode=PiExtractionMode.RECORDED,
            materializations=(PiMaterialization.DAILY,),
        ),
    )
    monkeypatch.setattr(provider, 'DEFINITIONS', definitions)

    catalog = provider.build_catalog()

    assert catalog.definitions == definitions
    assert provider.active_extraction_modes(catalog) == (
        PiExtractionMode.INTERPOLATED,
        PiExtractionMode.RECORDED,
    )
