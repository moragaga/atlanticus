# Compatibilidad pública: la policy pura vive ahora en ada.web.content_state.
from ada.web.content_state import (
    SourceFreshnessCondition,
    resolve_content_state_from_freshness,
)

__all__ = ['SourceFreshnessCondition', 'resolve_content_state_from_freshness']
