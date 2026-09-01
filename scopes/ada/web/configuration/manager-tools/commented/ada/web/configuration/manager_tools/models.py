from __future__ import annotations

from ada.configuration.branding import BrandingConfiguration, BrandingVariant

# Las etiquetas pertenecen a la presentación del Manager; la configuración conserva sólo la clave.
_BRANDING_LABELS = {
    BrandingVariant.ORIGINAL: 'Original',
    BrandingVariant.MINING_MONTH: 'Mes de la Minería',
    BrandingVariant.FIESTAS_PATRIAS: 'Fiestas Patrias',
    BrandingVariant.CHRISTMAS: 'Navidad',
    BrandingVariant.NEW_YEAR: 'Año Nuevo',
}


def branding_variant_options() -> tuple[dict[str, str], ...]:
    return tuple(
        {'label': _BRANDING_LABELS[variant], 'value': variant.value} for variant in BrandingVariant
    )


def build_branding_draft(variant_value: object) -> BrandingConfiguration:
    try:
        variant = BrandingVariant(variant_value)
    except (TypeError, ValueError) as error:
        raise ValueError('Branding variant is invalid') from error
    return BrandingConfiguration(variant=variant)
