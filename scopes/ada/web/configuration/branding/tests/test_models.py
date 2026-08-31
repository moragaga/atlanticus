import pytest

from ada.configuration.branding import (
    BrandingConfiguration,
    BrandingConfigurationValidationError,
    BrandingVariant,
)


def test_default_branding_is_original() -> None:
    assert BrandingConfiguration().variant is BrandingVariant.ORIGINAL


@pytest.mark.parametrize(
    'variant',
    tuple(BrandingVariant),
)
def test_all_supported_manual_variants_round_trip(variant: BrandingVariant) -> None:
    configuration = BrandingConfiguration(variant=variant)

    assert BrandingConfiguration.from_document(configuration.to_document()) == configuration


def test_empty_document_reads_as_original() -> None:
    assert BrandingConfiguration.from_document({}) == BrandingConfiguration()


def test_unknown_variant_is_rejected() -> None:
    with pytest.raises(
        BrandingConfigurationValidationError,
        match='Branding Configuration contract is invalid',
    ):
        BrandingConfiguration.from_document({'variant': 'automatic_by_date'})
