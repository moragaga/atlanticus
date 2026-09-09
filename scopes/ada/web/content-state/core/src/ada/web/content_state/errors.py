class ContentStateDependencyError(ValueError):
    pass


class MissingSourceFreshnessError(ContentStateDependencyError):
    pass
