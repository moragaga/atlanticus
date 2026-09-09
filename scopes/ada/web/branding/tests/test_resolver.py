import pytest

from ada.web.branding import BrandingConfiguration, BrandingVariant
from ada.web.branding.web import (
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
    resolve_branding_assets,
)


@pytest.mark.parametrize('variant', tuple(BrandingVariant))
def test_every_supported_variant_resolves_without_inventing_missing_assets(
    variant: BrandingVariant,
) -> None:
    assets = resolve_branding_assets(BrandingConfiguration(variant=variant))

    assert assets.requested_variant is variant
    assert assets.resolved_variant is BrandingVariant.ORIGINAL
    assert assets.operational_logo_src == DEFAULT_OPERATIONAL_BRAND_LOGO_SRC
    assert assets.navigation_logo_src == DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC
    assert assets.partner_logo_src == DEFAULT_PELAMBRES_BRAND_LOGO_SRC


def test_resolver_requires_branding_configuration() -> None:
    with pytest.raises(TypeError, match='requires BrandingConfiguration'):
        resolve_branding_assets(object())  # type: ignore[arg-type]
