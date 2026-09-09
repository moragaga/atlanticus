# Espejo comentado: API pública pura de Branding; no depende de Dash ni de Tool Configuration.
from ada.web.branding.errors import BrandingConfigurationValidationError
from ada.web.branding.models import BrandingConfiguration, BrandingVariant

__all__ = [
    'BrandingConfiguration',
    'BrandingConfigurationValidationError',
    'BrandingVariant',
]
