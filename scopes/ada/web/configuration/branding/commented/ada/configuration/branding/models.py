from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ada.configuration.branding.errors import BrandingConfigurationValidationError


# Las variantes son manuales: no existe activación automática por fecha.
class BrandingVariant(StrEnum):
    ORIGINAL = 'original'
    MINING_MONTH = 'mining_month'
    FIESTAS_PATRIAS = 'fiestas_patrias'
    CHRISTMAS = 'christmas'
    NEW_YEAR = 'new_year'


@dataclass(frozen=True, slots=True)
class BrandingConfiguration:
    # Original es el estado seguro cuando aún no existe configuración persistida.
    variant: BrandingVariant = BrandingVariant.ORIGINAL

    def __post_init__(self) -> None:
        if not isinstance(self.variant, BrandingVariant):
            raise BrandingConfigurationValidationError('Branding variant is invalid')

    def to_document(self) -> dict[str, str]:
        return {'variant': self.variant.value}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> BrandingConfiguration:
        try:
            # Compatibilidad de lectura: un documento vacío representa el logo original.
            return cls(variant=BrandingVariant(document.get('variant', 'original')))
        except (TypeError, ValueError) as error:
            raise BrandingConfigurationValidationError(
                'Branding Configuration contract is invalid'
            ) from error
