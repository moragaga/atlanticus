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
