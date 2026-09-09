# Espejo comentado: resuelve una variante semántica de Branding a assets Web disponibles.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.branding import BrandingConfiguration, BrandingVariant
from ada.web.branding.web.module import (
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
)


@dataclass(frozen=True, slots=True)
class BrandingAssetSet:
    # Se conserva la variante solicitada para diagnóstico y futura disponibilidad de assets.
    requested_variant: BrandingVariant
    # Mientras no existan assets temáticos físicos, la variante efectivamente resuelta es Normal.
    resolved_variant: BrandingVariant
    operational_logo_src: str
    navigation_logo_src: str
    partner_logo_src: str


def resolve_branding_assets(configuration: BrandingConfiguration) -> BrandingAssetSet:
    if not isinstance(configuration, BrandingConfiguration):
        raise TypeError('Branding asset resolution requires BrandingConfiguration')
    # W-ARCH-001 no inventa logos temáticos: todas las variantes válidas usan los assets Normal existentes.
    return BrandingAssetSet(
        requested_variant=configuration.variant,
        resolved_variant=BrandingVariant.ORIGINAL,
        operational_logo_src=DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
        navigation_logo_src=DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
        partner_logo_src=DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
    )
