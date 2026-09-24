from atlanticus.integrations.pi.contracts import (
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
    PiWebApiSource,
)

SOURCE = PiWebApiSource(interpolation_seconds=10)

DEFINITIONS: tuple[PiTagDefinition, ...] = ()
