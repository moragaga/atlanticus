import pytest

from ada.configuration.branding import BrandingVariant
from ada.web.configuration.manager_tools import branding_variant_options, build_branding_draft


def test_branding_options_expose_all_manual_variants() -> None:
    options = branding_variant_options()

    assert tuple(option['value'] for option in options) == tuple(
        variant.value for variant in BrandingVariant
    )
    assert tuple(option['label'] for option in options) == (
        'Original',
        'Mes de la Minería',
        'Fiestas Patrias',
        'Navidad',
        'Año Nuevo',
    )


@pytest.mark.parametrize('variant', tuple(BrandingVariant))
def test_branding_draft_is_manual_and_exact(variant: BrandingVariant) -> None:
    assert build_branding_draft(variant.value).variant is variant


def test_unknown_branding_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match='Branding variant is invalid'):
        build_branding_draft('auto')
