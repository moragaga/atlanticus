# Este módulo define únicamente el vocabulario de errores público de Source.
# Los proveedores traducen sus excepciones técnicas a estos errores para no filtrar detalles.
class SourceError(Exception):
    pass


class SourceReleaseNotFoundError(SourceError):
    pass


class SourceConcurrencyError(SourceError):
    pass


class SourceCorruptionError(SourceError):
    pass


class SourceUnavailableError(SourceError):
    pass


class SourceInvalidCursorError(SourceError):
    pass
